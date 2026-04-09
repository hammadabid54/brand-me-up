"""
Google OAuth authentication and dashboard views for client dashboard.
"""
import json
from datetime import datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import logout as auth_logout
from django.conf import settings
from django.utils import timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from core.models import Client, ClientConnection


def build_google_client_config(redirect_uri):
    """Build Google OAuth client config dict — DRY helper"""
    return {
        'web': {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'redirect_uris': [redirect_uri],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }


def login(request):
    """Initiate Google OAuth login"""
    redirect_uri = request.build_absolute_uri('/auth/callback/')
    client_config = build_google_client_config(redirect_uri)
    flow = Flow.from_client_config(client_config, scopes=settings.GOOGLE_SCOPES)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    """Handle OAuth callback"""
    error = request.GET.get('error')
    if error:
        return redirect('/dashboard/?error=' + error)

    code = request.GET.get('code')
    if not code:
        return redirect('/dashboard/?error=no_code')

    # CSRF state validation
    state = request.GET.get('state')
    stored_state = request.session.get('oauth_state')
    if state and stored_state and state != stored_state:
        return redirect('/dashboard/?error=state_mismatch')

    try:
        redirect_uri = request.build_absolute_uri('/auth/callback/')
        client_config = build_google_client_config(redirect_uri)
        flow = Flow.from_client_config(client_config, scopes=settings.GOOGLE_SCOPES)
        flow.fetch_token(code=code)
        credentials = flow.credentials

        userinfo_service = build('oauth2', 'v2', credentials=credentials)
        userinfo = userinfo_service.userinfo().get().execute()

        client, created = Client.objects.update_or_create(
            google_id=userinfo['id'],
            defaults={
                'email': userinfo['email'],
                'name': userinfo.get('name', userinfo['email']),
                'profile_picture': userinfo.get('picture', ''),
                'last_login': timezone.now()
            }
        )

        request.session['client_id'] = client.id
        request.session['client_email'] = client.email
        request.session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes)
        }

        # Clear OAuth state after successful auth
        request.session.pop('oauth_state', None)

        return redirect('/dashboard/')

    except Exception as e:
        return redirect('/dashboard/?error=auth_failed')


def logout_view(request):
    """Logout client"""
    # Clear session
    client_id = request.session.get('client_id')
    auth_logout(request)
    request.session.flush()
    return redirect('/')


# Dashboard views
def dashboard(request):
    """Main dashboard view"""
    client_id = request.session.get('client_id')

    # Demo mode - show a sample dashboard without login
    if not client_id:
        class DemoClient:
            id = None
            name = "Demo User"
            email = "demo@example.com"
            profile_picture = ""
        class DemoConnection:
            def __init__(self, svc, connected):
                self.service = svc
                self.is_connected = connected
        context = {
            'client': DemoClient(),
            'connections': [
                DemoConnection('analytics', True),
                DemoConnection('search_console', True),
                DemoConnection('gbp', True),
            ],
            'demo_mode': True,
        }
        return render(request, 'dashboard/index.html', context)

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return redirect('/auth/login/')


def scheduler(request):
    """Social media scheduler view"""
    return render(request, 'dashboard/scheduler.html')


def connect_service(request, service):
    """Connect a specific Google service"""
    client_id = request.session.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'Not logged in'}, status=401)

    # Define scopes for each service
    service_scopes = {
        'analytics': [
            'https://www.googleapis.com/auth/analytics.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
        ],
        'search_console': [
            'https://www.googleapis.com/auth/webmasters.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
        ],
        'gbp': [
            'https://www.googleapis.com/auth/business.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
        ],
    }

    if service not in service_scopes:
        return JsonResponse({'error': 'Invalid service'}, status=400)

    # Create custom flow for specific service
    redirect_uri = request.build_absolute_uri(f'/dashboard/connect/{service}/callback/')
    client_config = {
        'web': {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'redirect_uris': [redirect_uri, f'http://127.0.0.1:8000/dashboard/connect/{service}/callback/', f'http://localhost:8000/dashboard/connect/{service}/callback/'],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=service_scopes[service]
    )

    # Store service in session for callback
    request.session['connecting_service'] = service
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    request.session[f'connect_{service}_state'] = state

    return redirect(authorization_url)


def connect_service_callback(request, service):
    """Handle service connection callback"""
    client_id = request.session.get('client_id')
    if not client_id:
        return redirect('/dashboard/?error=not_logged_in')

    code = request.GET.get('code')
    if not code:
        return redirect('/dashboard/?error=no_code')

    try:
        redirect_uri = request.build_absolute_uri(f'/dashboard/connect/{service}/callback/')
        client_config = {
            'web': {
                'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                'redirect_uris': [redirect_uri, f'http://127.0.0.1:8000/dashboard/connect/{service}/callback/', f'http://localhost:8000/dashboard/connect/{service}/callback/'],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        }

        flow = Flow.from_client_config(client_config, scopes=[])
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Save or update connection
        ClientConnection.objects.update_or_create(
            client_id=client_id,
            service=service,
            defaults={
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token or '',
                'token_expiry': datetime.fromtimestamp(credentials.expiry) if credentials.expiry else None,
                'is_connected': True,
            }
        )

        return redirect('/dashboard/?connected=' + service)

    except Exception as e:
        return redirect('/dashboard/?error=' + str(e))


def get_credentials(client):
    """Get valid credentials for a client and service"""
    connections = ClientConnection.objects.filter(client=client, is_connected=True)

    creds_dict = {}
    for conn in connections:
        if conn.refresh_token:
            creds_dict[conn.service] = Credentials(
                token=conn.access_token,
                refresh_token=conn.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=settings.GOOGLE_SCOPES
            )
    return creds_dict


# API endpoints for dashboard data
def get_analytics_data(request):
    """Get Google Analytics data"""
    client_id = request.session.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)

    # Get credentials
    connections = ClientConnection.objects.filter(client=client, service='analytics', is_connected=True)
    if not connections:
        return JsonResponse({'error': 'Analytics not connected'}, status=400)

    conn = connections.first()
    if not conn.access_token:
        return JsonResponse({'error': 'No valid credentials'}, status=400)

    try:
        from google.analytics.data import BetaAnalyticsDataClient

        creds = Credentials(
            token=conn.access_token,
            refresh_token=conn.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        )

        client = BetaAnalyticsDataClient(credentials=creds)

        # Run report
        response = client.run_report(
            property=f"properties/{conn.property_id or 'YOUR_PROPERTY_ID'}",
            date_ranges=[{'start_date': '7daysAgo', 'end_date': 'today'}],
            dimensions=[{'name': 'date'}],
            metrics=[
                {'name': 'sessions'},
                {'name': 'totalUsers'},
                {'name': 'pageviews'},
                {'name': 'bounceRate'},
            ]
        )

        data = []
        for row in response.rows:
            data.append({
                'date': row.dimension_values[0].value,
                'sessions': row.metric_values[0].value,
                'users': row.metric_values[1].value,
                'pageviews': row.metric_values[2].value,
                'bounce_rate': row.metric_values[3].value,
            })

        return JsonResponse({'success': True, 'data': data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_search_console_data(request):
    """Get Google Search Console data"""
    client_id = request.session.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)

    # Get credentials
    connections = ClientConnection.objects.filter(client=client, service='search_console', is_connected=True)
    if not connections:
        return JsonResponse({'error': 'Search Console not connected'}, status=400)

    conn = connections.first()
    if not conn.access_token:
        return JsonResponse({'error': 'No valid credentials'}, status=400)

    try:
        creds = Credentials(
            token=conn.access_token,
            refresh_token=conn.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        )

        service = build('searchconsole', 'v1', credentials=creds)

        # Get search analytics
        site_url = conn.property_id or ''
        response = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                'startDate': '28daysAgo',
                'endDate': 'today',
                'dimensions': ['query', 'page', 'country'],
                'rowLimit': 50
            }
        ).execute()

        return JsonResponse({'success': True, 'data': response.get('rows', [])})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_gbp_data(request):
    """Get Google Business Profile data"""
    client_id = request.session.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)

    # Get credentials
    connections = ClientConnection.objects.filter(client=client, service='gbp', is_connected=True)
    if not connections:
        return JsonResponse({'error': 'GBP not connected'}, status=400)

    conn = connections.first()
    if not conn.access_token:
        return JsonResponse({'error': 'No valid credentials'}, status=400)

    try:
        creds = Credentials(
            token=conn.access_token,
            refresh_token=conn.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        )

        # Note: GBP API requires additional setup
        # This is a placeholder for the actual implementation
        return JsonResponse({
            'success': True,
            'data': {
                'views': 0,
                'searches': 0,
                'directions': 0,
                'calls': 0,
                'note': 'GBP API integration requires additional Google Business Profile API setup'
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def disconnect_service(request, service):
    """Disconnect a Google service"""
    client_id = request.session.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        connection = ClientConnection.objects.get(client_id=client_id, service=service)
        connection.is_connected = False
        connection.save()
        return JsonResponse({'success': True})
    except ClientConnection.DoesNotExist:
        return JsonResponse({'error': 'Connection not found'}, status=404)


@require_http_methods(["GET"])
def get_connected_platforms(request):
    """Get list of connected social platforms for the client"""
    client_id = request.session.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)

    social_services = ['meta_facebook', 'meta_instagram', 'linkedin', 'twitter']
    connections = ClientConnection.objects.filter(client=client, service__in=social_services)
    connected = {conn.service: conn.is_connected for conn in connections}
    return JsonResponse({'success': True, 'connected': connected})


# Social platform OAuth URLs
SOCIAL_OAUTH_URLS = {
    'meta_facebook': '/auth/social/facebook/',
    'meta_instagram': '/auth/social/instagram/',
    'linkedin': '/auth/social/linkedin/',
    'pinterest': '/auth/social/pinterest/',
}


@require_http_methods(["GET"])
def social_login(request, platform):
    """Initiate OAuth for a social platform"""
    if platform not in SOCIAL_OAUTH_URLS:
        return JsonResponse({'error': 'Invalid platform'}, status=400)

    # Map scheduler platform names to ClientConnection service names
    platform_to_service = {
        'facebook': 'meta_facebook',
        'instagram': 'meta_instagram',
        'linkedin': 'linkedin',
        'pinterest': 'pinterest',
    }
    service = platform_to_service.get(platform)
    if not service:
        return JsonResponse({'error': 'Invalid platform'}, status=400)

    # Store the platform being connected in session
    request.session['connecting_platform'] = platform
    request.session['connecting_service'] = service

    return JsonResponse({
        'success': True,
        'redirect_url': f'/auth/social/{platform}/initiate/',
        'platform': platform,
    })


@require_http_methods(["GET"])
def social_callback(request, platform):
    """Handle OAuth callback for social platforms"""
    client_id = request.session.get('client_id')
    if not client_id:
        return redirect('/auth/login/')

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return redirect('/auth/login/')

    service = request.session.get('connecting_service')
    code = request.GET.get('code')

    if not code:
        return redirect('/dashboard/scheduler/?error=no_code')

    # Platform-specific token exchange
    # Each platform has different OAuth endpoints and token formats
    try:
        if service == 'meta_facebook':
            return _handle_meta_callback(client, request, code, 'meta_facebook')
        elif service == 'meta_instagram':
            return _handle_meta_callback(client, request, code, 'meta_instagram')
        elif service == 'linkedin':
            return _handle_linkedin_callback(client, request, code)
        elif service == 'pinterest':
            return _handle_pinterest_callback(client, request, code)
    except Exception as e:
        return redirect(f'/dashboard/scheduler/?error={str(e)}')

    return redirect('/dashboard/scheduler/?connected=' + platform)


def _handle_meta_callback(client, request, code, service):
    """Handle Meta (Facebook/Instagram) OAuth callback"""
    try:
        import requests
        from django.conf import settings

        redirect_uri = request.build_absolute_uri(f'/auth/social/callback/{service.replace("meta_", "")}/')

        # Exchange code for tokens
        token_url = 'https://graph.facebook.com/v19.0/oauth/access_token'
        response = requests.get(token_url, params={
            'client_id': settings.META_OAUTH_CLIENT_ID,
            'client_secret': settings.META_OAUTH_CLIENT_SECRET,
            'code': code,
            'redirect_uri': redirect_uri,
        }, timeout=30)

        if not response.ok:
            raise Exception(f'Meta token exchange failed: {response.text}')

        data = response.json()
        access_token = data.get('access_token')

        if not access_token:
            raise Exception('No access token in Meta response')

        # Store connection
        ClientConnection.objects.update_or_create(
            client=client,
            service=service,
            defaults={
                'access_token': access_token,
                'refresh_token': data.get('refresh_token', ''),
                'is_connected': True,
            }
        )

        return redirect('/dashboard/scheduler/?connected=' + service.replace('meta_', ''))

    except Exception as e:
        logger.error(f'Meta OAuth error: {e}')
        return redirect(f'/dashboard/scheduler/?error={str(e)}')


def _handle_linkedin_callback(client, request, code):
    """Handle LinkedIn OAuth callback"""
    try:
        import requests
        from django.conf import settings

        redirect_uri = request.build_absolute_uri('/auth/social/callback/linkedin/')

        # Exchange code for tokens
        token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
        response = requests.post(token_url, data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': settings.LINKEDIN_OAUTH_CLIENT_ID,
            'client_secret': settings.LINKEDIN_OAUTH_CLIENT_SECRET,
        }, timeout=30)

        if not response.ok:
            raise Exception(f'LinkedIn token exchange failed: {response.text}')

        data = response.json()
        access_token = data.get('access_token')

        if not access_token:
            raise Exception('No access token in LinkedIn response')

        ClientConnection.objects.update_or_create(
            client=client,
            service='linkedin',
            defaults={
                'access_token': access_token,
                'refresh_token': data.get('refresh_token', ''),
                'is_connected': True,
            }
        )

        return redirect('/dashboard/scheduler/?connected=linkedin')

    except Exception as e:
        logger.error(f'LinkedIn OAuth error: {e}')
        return redirect(f'/dashboard/scheduler/?error={str(e)}')


def _handle_pinterest_callback(client, request, code):
    """Handle Pinterest OAuth callback"""
    try:
        import requests
        from django.conf import settings

        redirect_uri = request.build_absolute_uri('/auth/social/callback/pinterest/')

        # Exchange code for tokens
        token_url = 'https://api.pinterest.com/v5/oauth/token'
        response = requests.post(token_url, data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
        }, params={
            'client_id': settings.PINTEREST_OAUTH_CLIENT_ID,
            'client_secret': settings.PINTEREST_OAUTH_CLIENT_SECRET,
        }, timeout=30)

        if not response.ok:
            raise Exception(f'Pinterest token exchange failed: {response.text}')

        data = response.json()
        access_token = data.get('access_token')

        if not access_token:
            raise Exception('No access token in Pinterest response')

        ClientConnection.objects.update_or_create(
            client=client,
            service='pinterest',
            defaults={
                'access_token': access_token,
                'refresh_token': data.get('refresh_token', ''),
                'is_connected': True,
            }
        )

        return redirect('/dashboard/scheduler/?connected=pinterest')

    except Exception as e:
        logger.error(f'Pinterest OAuth error: {e}')
        return redirect(f'/dashboard/scheduler/?error={str(e)}')

