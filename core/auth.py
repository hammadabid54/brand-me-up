"""
Client dashboard authentication and views.

Phase 1: Email/password auth with email verification, password reset,
protected dashboard with parallel auth (existing Google OAuth users + new User accounts).

Parallel auth: get_client() checks Django User auth first, then falls back to
session-based Google OAuth for existing users.
"""
import logging
import random
import secrets
import string
from datetime import datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib.auth import logout as auth_logout, login, get_user_model, authenticate
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.template.loader import render_to_string

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from core.models import Client, ClientConnection
from core.backends import email_to_username

User = get_user_model()

logger = logging.getLogger(__name__)


# ==================== Auth Backend ====================

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


def build_google_credentials(access_token, refresh_token=None, scopes=None):
    """Build a google-auth Credentials object from stored token data.

    Checks token expiry and returns None if expired (so caller can handle refresh).
    """
    from django.utils import timezone
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=scopes or settings.GOOGLE_SCOPES,
    )
    # Expiry is set automatically by google-auth when token is created
    # If we have a refresh_token, the Credentials object can self-refresh
    return creds


# ==================== Parallel Auth Helper ====================

def get_client(request):
    """Get Client from Django auth OR Google OAuth session (parallel auth).

    Supports both:
    - New email/password users: request.user.is_authenticated=True -> user.client_profile
    - Existing Google OAuth users: request.user.is_authenticated=False, client_id in session

    Returns None if neither path yields a Client, caller should redirect.
    """
    if request.user.is_authenticated:
        client = getattr(request.user, 'client_profile', None)
        if client:
            return client
        return None

    client_id = request.session.get('client_id')
    if client_id:
        return Client.objects.filter(id=client_id).first()
    return None


# ==================== Email/Password Login View ====================

@csrf_protect
def login_view(request):
    """Email/password login with remember_me support."""
    if request.user.is_authenticated:
        return redirect('/dashboard/')

    if request.method == 'POST':
        # Use custom backend directly — allows inactive users (for email verification flow)
        # AuthenticationForm rejects inactive users at form.is_valid() time, which prevents
        # us from showing the specific "verify your email" error.
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                remember_me = request.POST.get('remember_me') == 'on'
                if remember_me:
                    request.session.set_expiry(60 * 60 * 24 * 14)  # 2 weeks
                else:
                    request.session.set_expiry(60 * 60 * 24 * 7)   # 1 week
                next_url = request.GET.get('next', '/dashboard/')
                if request.GET.get('verified'):
                    next_url = '/dashboard/'
                return redirect(next_url)
            else:
                # Unverified user with correct credentials — specific error
                form = AuthenticationForm(request)
                return render(request, 'account/login.html', {
                    'form': form,
                    'errors': {'general': ['Please verify your email first. Check your inbox for the verification link.']},
                })
        else:
            # Wrong credentials (or non-existent user) — vague error to prevent enumeration
            form = AuthenticationForm(request)
            return render(request, 'account/login.html', {
                'form': form,
                'errors': {'general': ['Invalid email or password.']},
            })
    else:
        form = AuthenticationForm(request)

    context = {'form': form}
    if request.GET.get('verified'):
        context['success_message'] = 'Email verified! Please log in.'
    if request.GET.get('set_password'):
        context['success_message'] = 'Password set! Please log in with your email and new password.'
    return render(request, 'account/login.html', context)


# ==================== Google OAuth (existing, unchanged) ====================

def google_login(request):
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

        request.session.pop('oauth_state', None)
        return redirect('/dashboard/')

    except Exception as e:
        return redirect('/dashboard/?error=auth_failed')


def logout_view(request):
    """Logout client"""
    auth_logout(request)
    request.session.flush()
    return redirect('/')


# ==================== Email/Password Auth Views ====================

@csrf_protect
def signup_view(request):
    """Handle email/password signup with email verification."""
    if request.user.is_authenticated:
        return redirect('/dashboard/')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        first_name = request.POST.get('first_name', '').strip()

        errors = {}

        if not email or '@' not in email:
            errors['email'] = 'Please enter a valid email address.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists. Log in or use a different email.'

        if not password:
            errors['password'] = 'Please enter a password.'
        elif len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif password != password_confirm:
            errors['password_confirm'] = 'Passwords do not match.'

        if errors:
            context = {'email': email, 'first_name': first_name, 'errors': errors}
            return render(request, 'account/signup.html', context, status=400)

        # Create User
        username = email_to_username(email)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            is_active=False
        )

        # Create or link Client
        client = Client.objects.create(
            user=user,
            email=email,
            name=first_name or f'Guest {user.id}',
        )

        # Send verification email
        _send_verification_email(request, user, email)

        return render(request, 'account/verification_sent.html', {
            'email': email,
        })

    return render(request, 'account/signup.html')


def _send_verification_email(request, user, email):
    """Generate verification token and send email."""
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        f'/auth/verify/{uidb64}/{token}/'
    )

    subject = 'Verify your Omni Path Marketing dashboard account'
    message = render_to_string('account/email/verify_email.txt', {
        'user': user,
        'verify_url': verify_url,
    })
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
    except Exception as e:
        logger.error(f'Failed to send verification email to {email}: {e}')


def verify_email(request, uidb64, token):
    """Verify email address and activate account."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, User.DoesNotExist):
        return render(request, 'account/verify_error.html', {
            'error': 'link_invalid',
            'message': 'This verification link is invalid. It may have already been used or expired.'
        })

    if not default_token_generator.check_token(user, token):
        return render(request, 'account/verify_error.html', {
            'error': 'link_invalid',
            'message': 'This verification link has expired or was already used.'
        })

    if user.is_active:
        return render(request, 'account/verify_error.html', {
            'error': 'link_invalid',
            'message': 'This verification link has already been used.'
        })

    user.is_active = True
    user.save()
    return redirect('/auth/login/?verified=1')


@csrf_protect
def set_password_view(request):
    """Set password for Google OAuth users to enable email/password login."""
    client = get_client(request)
    if not client:
        return redirect('/auth/login/')

    # Only Google OAuth users can set password here (they have google_id)
    if not client.google_id:
        return redirect('/dashboard/')

    if request.method == 'POST':
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = {}
        if not password or len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif password != password_confirm:
            errors['password_confirm'] = 'Passwords do not match.'

        if not errors:
            user = client.user
            if not user:
                return render(request, 'account/set_password.html', {
                    'errors': {'general': 'Account error. Please contact support.'}
                })
            user.set_password(password)
            user.save()
            return redirect('/auth/login/?set_password=1')

        return render(request, 'account/set_password.html', {'errors': errors})

    return render(request, 'account/set_password.html')


# ==================== Agency Invite Magic Link (GAP 6) ====================

def _generate_invite_token():
    """Generate a secure random invite token."""
    return secrets.token_urlsafe(32)


def _send_agency_invite_email(client, invite_url, agency_name):
    """Send an invite email to a newly added agency client."""
    subject = f'{agency_name} has invited you to their client dashboard'
    message = render_to_string('account/email/agency_invite.txt', {
        'client': client,
        'invite_url': invite_url,
        'agency_name': agency_name,
    })
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [client.email])
    except Exception as e:
        logger.error(f'Failed to send agency invite email to {client.email}: {e}')


@csrf_protect
def invite_accept(request, token):
    """Handle agency invite link — set password and activate account."""
    # Find client with this invite token
    client = Client.objects.filter(invite_token=token).first()
    if not client:
        return render(request, 'account/invite_error.html', {
            'error': 'link_invalid',
            'message': 'This invite link is invalid or has already been used.',
        })

    # Check expiry (72 hours)
    if client.invite_token_expiry and timezone.now() > client.invite_token_expiry:
        return render(request, 'account/invite_error.html', {
            'error': 'link_expired',
            'message': 'This invite link has expired. Ask your agency to send a new one.',
        })

    # If already activated
    if client.user and client.user.is_active:
        return redirect('/auth/login/?already_activated=1')

    if request.method == 'POST':
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        errors = {}

        if not password or len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif password != password_confirm:
            errors['password_confirm'] = 'Passwords do not match.'

        if errors:
            return render(request, 'account/invite_accept.html', {
                'client': client,
                'errors': errors,
            })

        # Create user if not exists
        if not client.user:
            username = email_to_username(client.email)
            user = User.objects.create_user(
                username=username,
                email=client.email,
                password=password,
                is_active=True,
            )
            client.user = user
            client.invite_token = None
            client.invite_token_expiry = None
            client.save()
        else:
            client.user.set_password(password)
            client.user.is_active = True
            client.user.save()
            client.invite_token = None
            client.invite_token_expiry = None
            client.save()

        return redirect('/auth/login/?invite_accepted=1')

    return render(request, 'account/invite_accept.html', {'client': client})


@require_http_methods(["GET", "POST"])
def agency_clients(request):
    """Agency client management — list, add, and invite managed clients."""
    client = get_client(request)
    if not client:
        return redirect('/auth/login/?next=/dashboard/clients/')

    # List agency's managed clients
    managed_clients = Client.objects.filter(agency=client, is_agency_client=True)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        errors = {}

        if not name:
            errors['name'] = 'Name is required.'
        if not email or '@' not in email:
            errors['email'] = 'A valid email address is required.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists.'
        elif Client.objects.filter(email=email).exists():
            errors['email'] = 'A client with this email already exists.'

        if errors:
            return render(request, 'dashboard/clients.html', {
                'client': client,
                'managed_clients': managed_clients,
                'add_errors': errors,
            })

        # Create invite token (72h expiry)
        from datetime import timedelta
        invite_token = _generate_invite_token()
        invite_url = request.build_absolute_uri(f'/auth/invite/{invite_token}/')

        new_client = Client.objects.create(
            email=email,
            name=name,
            is_agency_client=True,
            agency=client,
            invite_token=invite_token,
            invite_token_expiry=timezone.now() + timedelta(hours=72),
            invite_sent_at=timezone.now(),
            is_active=False,
        )

        # Send invite email
        _send_agency_invite_email(new_client, invite_url, client.name)

        return redirect('/dashboard/clients/?added=1')

    return render(request, 'dashboard/clients.html', {
        'client': client,
        'managed_clients': managed_clients,
    })


# ==================== Dashboard Views (updated) ====================

def dashboard(request):
    """Main dashboard view — supports parallel auth."""
    client = get_client(request)
    if not client:
        return redirect('/auth/login/?next=/dashboard/')

    try:
        client = Client.objects.get(id=client.id)
    except Client.DoesNotExist:
        return redirect('/auth/login/')

    # Fetch connections
    connections = ClientConnection.objects.filter(client=client, is_connected=True)
    connections_by_service = {c.service: c for c in connections}

    context = {
        'client': client,
        'connections': connections_by_service,
        # Individual booleans for template checks
        'analytics_connected': 'analytics' in connections_by_service,
        'search_console_connected': 'search_console' in connections_by_service,
        'gbp_connected': 'gbp' in connections_by_service,
        'is_agency_client': client.is_agency_client,
        'last_updated': timezone.now(),
    }
    return render(request, 'dashboard/index.html', context)


def scheduler(request):
    """Social media scheduler view — paid users only."""
    client = get_client(request)
    if not client:
        return redirect('/auth/login/?next=/dashboard/scheduler/')
    if not client.is_agency_client:
        return redirect('/dashboard/?upgrade=scheduler')
    return render(request, 'dashboard/scheduler.html')


# ==================== Google OAuth Service Connect (existing, unchanged) ====================

def connect_service(request, service):
    """Connect a specific Google service"""
    client = get_client(request)
    if not client:
        return redirect('/auth/login/?next=' + request.path)

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
        return redirect('/dashboard/?error=invalid_service')

    redirect_uri = request.build_absolute_uri(f'/dashboard/connect/{service}/callback/')
    client_config = build_google_client_config(redirect_uri)
    flow = Flow.from_client_config(client_config, scopes=service_scopes[service])
    request.session['connecting_service'] = service
    # Store client_id for callback — works for both Google OAuth users and email/password users
    request.session['client_id'] = client.id
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    request.session[f'connect_{service}_state'] = state
    request.session[f'connect_{service}_scopes'] = service_scopes[service]
    return redirect(authorization_url)


def connect_service_callback(request, service):
    """Handle service connection callback"""
    # Try session client_id (set during connect_service for both Google OAuth and email/password users)
    client_id = request.session.get('client_id')
    if not client_id:
        # Fall back to get_client for parallel auth
        client = get_client(request)
        if not client:
            return redirect('/dashboard/?error=not_logged_in')
        client_id = client.id

    code = request.GET.get('code')
    state = request.GET.get('state')
    if not code:
        return redirect('/dashboard/?error=no_code')

    # Validate state (CSRF protection)
    stored_state = request.session.get(f'connect_{service}_state')
    if state and stored_state and state != stored_state:
        return redirect('/dashboard/?error=state_mismatch')

    # Retrieve the original scopes stored during initiation
    stored_scopes = request.session.get(f'connect_{service}_scopes', [])

    try:
        redirect_uri = request.build_absolute_uri(f'/dashboard/connect/{service}/callback/')
        client_config = build_google_client_config(redirect_uri)
        flow = Flow.from_client_config(client_config, scopes=stored_scopes)
        flow.fetch_token(code=code, state=stored_state)
        credentials = flow.credentials

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
            creds_dict[conn.service] = build_google_credentials(
                access_token=conn.access_token,
                refresh_token=conn.refresh_token,
                scopes=settings.GOOGLE_SCOPES,
            )
    return creds_dict


# ==================== Dashboard API ====================

def get_analytics_data(request):
    """Get Google Analytics data"""
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    connections = ClientConnection.objects.filter(client=client, service='analytics', is_connected=True)
    if not connections:
        return JsonResponse({'error': 'Analytics not connected'}, status=400)

    conn = connections.first()
    if not conn.access_token:
        return JsonResponse({'error': 'No valid credentials'}, status=400)

    try:
        from google.analytics.data import BetaAnalyticsDataClient
        creds = build_google_credentials(conn.access_token, conn.refresh_token)
        client_ga = BetaAnalyticsDataClient(credentials=creds)
        response = client_ga.run_report(
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
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    connections = ClientConnection.objects.filter(client=client, service='search_console', is_connected=True)
    if not connections:
        return JsonResponse({'error': 'Search Console not connected'}, status=400)

    conn = connections.first()
    if not conn.access_token:
        return JsonResponse({'error': 'No valid credentials'}, status=400)

    try:
        creds = build_google_credentials(conn.access_token, conn.refresh_token)
        service_discovery = build('searchconsole', 'v1', credentials=creds)
        site_url = conn.property_id or ''
        response = service_discovery.searchanalytics().query(
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
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    connections = ClientConnection.objects.filter(client=client, service='gbp', is_connected=True)
    if not connections:
        return JsonResponse({'error': 'GBP not connected'}, status=400)

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


@require_http_methods(["POST"])
def disconnect_service(request, service):
    """Disconnect a Google service"""
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        connection = ClientConnection.objects.get(client=client, service=service)
        connection.is_connected = False
        connection.save()
        return JsonResponse({'success': True})
    except ClientConnection.DoesNotExist:
        return JsonResponse({'error': 'Connection not found'}, status=404)


@require_http_methods(["GET"])
def get_connected_platforms(request):
    """Get list of connected social platforms for the client"""
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    social_services = ['meta_facebook', 'meta_instagram', 'linkedin', 'pinterest']
    connections = ClientConnection.objects.filter(client=client, service__in=social_services)
    connected = {conn.service: conn.is_connected for conn in connections}
    return JsonResponse({'success': True, 'connected': connected})


# ==================== Password Reset Views (Django built-in) ====================

def password_reset(request):
    """Wrapper for Django's password reset — uses same token mechanism."""
    from django.contrib.auth.views import PasswordResetView
    return PasswordResetView.as_view(
        template_name='account/password_reset.html',
        email_template_name='account/email/password_reset_email.txt',
        subject_template_name='account/email/password_reset_subject.txt',
        success_url='/auth/password-reset/done/'
    )(request)


def password_reset_done(request):
    """Password reset email sent confirmation."""
    from django.contrib.auth.views import PasswordResetDoneView
    return PasswordResetDoneView.as_view(
        template_name='account/password_reset_done.html'
    )(request)


def password_reset_confirm(request, uidb64, token):
    """Set new password after reset."""
    from django.contrib.auth.views import PasswordResetConfirmView
    return PasswordResetConfirmView.as_view(
        template_name='account/password_reset_confirm.html',
        success_url='/auth/password-reset/complete/'
    )(request, uidb64=uidb64, token=token)


def password_reset_complete(request):
    """Password reset complete."""
    from django.contrib.auth.views import PasswordResetCompleteView
    return PasswordResetCompleteView.as_view(
        template_name='account/password_reset_complete.html'
    )(request)


# ==================== Social Platform OAuth (existing, unchanged) ====================

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

    platform_to_service = {
        'facebook': 'meta_facebook',
        'instagram': 'meta_instagram',
        'linkedin': 'linkedin',
        'pinterest': 'pinterest',
    }
    service = platform_to_service.get(platform)
    if not service:
        return JsonResponse({'error': 'Invalid platform'}, status=400)

    request.session['connecting_platform'] = platform
    request.session['connecting_service'] = service

    return JsonResponse({
        'success': True,
        'redirect_url': f'/auth/social/{platform}/initiate/',
        'platform': platform,
    })


PLATFORM_OAUTH_CONFIGS = {
    'facebook': {
        'auth_url': 'https://www.facebook.com/v19.0/dialog/oauth',
        'scope': 'pages_manage_metadata,instagram_basic,instagram_content_publish',
    },
    'instagram': {
        'auth_url': 'https://www.facebook.com/v19.0/dialog/oauth',
        'scope': 'pages_manage_metadata,instagram_basic,instagram_content_publish',
    },
    'linkedin': {
        'auth_url': 'https://www.linkedin.com/oauth/v2/authorization',
        'scope': 'w_member_social',
    },
    'pinterest': {
        'auth_url': 'https://api.pinterest.com/v5/oauth/authorize',
        'scope': 'boards:read,pins:read,pins:write',
    },
}


def social_oauth_initiate(request, platform):
    """Build the OAuth URL and redirect to the platform's authorization page.

    This is the endpoint that /auth/social/{platform}/initiate/ routes to.
    Generates a cryptographically random state parameter, stores it in session,
    and redirects to the platform's authorization URL.
    """
    if platform not in PLATFORM_OAUTH_CONFIGS:
        return redirect('/dashboard/scheduler/?error=invalid_platform')

    config = PLATFORM_OAUTH_CONFIGS[platform]
    service = request.session.get('connecting_service')
    if not service:
        return redirect('/dashboard/scheduler/?error=session_expired')

    # Generate and store state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    request.session['oauth_platform'] = platform

    # Build the authorization URL
    redirect_uri = request.build_absolute_uri(f'/auth/social/callback/{platform}/')

    if platform in ('facebook', 'instagram'):
        # Meta uses client_id as a query param
        auth_url = f"{config['auth_url']}?client_id={settings.META_OAUTH_CLIENT_ID}&redirect_uri={redirect_uri}&scope={config['scope']}&state={state}&response_type=code"
    elif platform == 'linkedin':
        auth_url = f"{config['auth_url']}?client_id={settings.LINKEDIN_OAUTH_CLIENT_ID}&redirect_uri={redirect_uri}&scope={config['scope']}&state={state}&response_type=code"
    elif platform == 'pinterest':
        auth_url = f"{config['auth_url']}?client_id={settings.PINTEREST_OAUTH_CLIENT_ID}&redirect_uri={redirect_uri}&scope={config['scope']}&state={state}&response_type=code"

    return redirect(auth_url)


@require_http_methods(["GET"])
def social_callback(request, platform):
    """Handle OAuth callback for social platforms"""
    client = get_client(request)
    if not client:
        return redirect('/auth/login/')

    service = request.session.get('connecting_service')
    code = request.GET.get('code')
    state = request.GET.get('state')

    if not code:
        return redirect('/dashboard/scheduler/?error=no_code')

    # Validate state parameter (CSRF protection)
    stored_state = request.session.get('oauth_state')
    if state and stored_state and state != stored_state:
        return redirect('/dashboard/scheduler/?error=state_mismatch')

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
        redirect_uri = request.build_absolute_uri(f'/auth/social/callback/{service.replace("meta_", "")}/')
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
        return redirect(f'/dashboard/scheduler/?error={str(e)}')


def _handle_linkedin_callback(client, request, code):
    """Handle LinkedIn OAuth callback"""
    try:
        import requests
        redirect_uri = request.build_absolute_uri('/auth/social/callback/linkedin/')
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
        return redirect(f'/dashboard/scheduler/?error={str(e)}')


def _handle_pinterest_callback(client, request, code):
    """Handle Pinterest OAuth callback"""
    try:
        import requests
        redirect_uri = request.build_absolute_uri('/auth/social/callback/pinterest/')
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
        return redirect(f'/dashboard/scheduler/?error={str(e)}')
