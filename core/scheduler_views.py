"""
Social media scheduler API views: CRUD for ScheduledPost.
"""
import logging
from datetime import datetime

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction

from core.models import Client, ClientConnection
from core.scheduler_models import ScheduledPost, ScheduledPlatform

logger = logging.getLogger(__name__)


def get_client(request):
    """Get client from session. Returns None if not logged in."""
    client_id = request.session.get('client_id')
    if not client_id:
        return None
    try:
        return Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return None


def require_auth(view_func):
    """Decorator: return 401 if client not authenticated"""
    def wrapper(request, *args, **kwargs):
        client = get_client(request)
        if not client:
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        request._client = client
        return view_func(request, *args, **kwargs)
    return wrapper


@csrf_exempt
@require_http_methods(['GET'])
def list_posts(request):
    """List scheduled posts for the authenticated client.

    Query params:
        platform: filter by platform (facebook, instagram, linkedin, twitter)
        status: filter by status (draft, scheduled, published, failed)
        from_date: filter posts scheduled after this date
        to_date: filter posts scheduled before this date
        page: pagination page number (default 1)
        page_size: items per page (default 20, max 100)
    """
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    queryset = ScheduledPost.objects.filter(client=client)

    # Filters
    platform = request.GET.get('platform')
    status = request.GET.get('status')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    if platform:
        queryset = queryset.filter(platform_posts__platform=platform)
    if status:
        queryset = queryset.filter(status=status)
    if from_date:
        queryset = queryset.filter(scheduled_time__gte=from_date)
    if to_date:
        queryset = queryset.filter(scheduled_time__lte=to_date)

    # Pagination
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 20))))
    except ValueError:
        page, page_size = 1, 20

    offset = (page - 1) * page_size
    total = queryset.count()
    posts = queryset.prefetch_related('platform_posts')[offset:offset + page_size]

    return JsonResponse({
        'success': True,
        'data': {
            'posts': [post_to_dict(p) for p in posts],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'pages': (total + page_size - 1) // page_size,
            }
        }
    })


@csrf_exempt
@require_http_methods(['POST'])
def create_post(request):
    """Create a new scheduled post.

    Body (JSON):
        content: str (required, max 2000 chars)
        media_urls: list of URLs (optional)
        link_url: str (optional)
        scheduled_time: ISO datetime string (optional — null for drafts)
        platforms: list of platform strings (required, at least one)
    """
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        import json
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    content = body.get('content', '').strip()
    if not content:
        return JsonResponse({'error': 'content is required'}, status=400)
    if len(content) > 2000:
        return JsonResponse({'error': 'content exceeds 2000 character limit'}, status=400)

    media_urls = body.get('media_urls', [])
    if not isinstance(media_urls, list):
        return JsonResponse({'error': 'media_urls must be a list'}, status=400)

    link_url = body.get('link_url', '')
    scheduled_time = None
    if body.get('scheduled_time'):
        try:
            scheduled_time = datetime.fromisoformat(
                body['scheduled_time'].replace('Z', '+00:00')
            )
        except ValueError:
            return JsonResponse({'error': 'invalid scheduled_time format'}, status=400)

    platforms = body.get('platforms', [])
    if not platforms or not isinstance(platforms, list):
        return JsonResponse({'error': 'at least one platform is required'}, status=400)
    valid_platforms = {p for p, _ in ScheduledPlatform.PLATFORM_CHOICES}
    for p in platforms:
        if p not in valid_platforms:
            return JsonResponse({'error': f'invalid platform: {p}'}, status=400)

    # Set status based on whether scheduled_time is set
    status = 'scheduled' if scheduled_time else 'draft'
    if scheduled_time and scheduled_time < timezone.now():
        return JsonResponse({'error': 'scheduled_time must be in the future'}, status=400)

    try:
        with transaction.atomic():
            post = ScheduledPost.objects.create(
                client=client,
                content=content,
                media_urls=media_urls,
                link_url=link_url,
                scheduled_time=scheduled_time,
                status=status,
            )
            for platform in platforms:
                ScheduledPlatform.objects.create(
                    post=post,
                    platform=platform,
                )

        return JsonResponse({
            'success': True,
            'data': post_to_dict(post)
        }, status=201)

    except Exception as e:
        logger.error(f'create_post error: {e}')
        return JsonResponse({'error': 'Failed to create post'}, status=500)


@csrf_exempt
@require_http_methods(['GET', 'PUT', 'DELETE'])
def post_detail(request, post_id):
    """Get, update, or delete a single post"""
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        post = ScheduledPost.objects.prefetch_related('platform_posts').get(
            id=post_id, client=client
        )
    except ScheduledPost.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'success': True, 'data': post_to_dict(post)})

    if request.method == 'DELETE':
        post.delete()
        return JsonResponse({'success': True})

    # PUT
    try:
        import json
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    content = body.get('content', '').strip()
    if content:
        if len(content) > 2000:
            return JsonResponse({'error': 'content exceeds 2000 chars'}, status=400)
        post.content = content

    if 'media_urls' in body:
        if not isinstance(body['media_urls'], list):
            return JsonResponse({'error': 'media_urls must be a list'}, status=400)
        post.media_urls = body['media_urls']

    if 'link_url' in body:
        post.link_url = body['link_url']

    if 'scheduled_time' in body:
        if body['scheduled_time']:
            try:
                post.scheduled_time = datetime.fromisoformat(
                    body['scheduled_time'].replace('Z', '+00:00')
                )
            except ValueError:
                return JsonResponse({'error': 'invalid scheduled_time'}, status=400)
        else:
            post.scheduled_time = None

    if 'platforms' in body:
        platforms = body['platforms']
        valid_platforms = {p for p, _ in ScheduledPlatform.PLATFORM_CHOICES}
        for p in platforms:
            if p not in valid_platforms:
                return JsonResponse({'error': f'invalid platform: {p}'}, status=400)
        # Replace platforms
        post.platform_posts.all().delete()
        for p in platforms:
            ScheduledPlatform.objects.create(post=post, platform=p)

    post.save()
    post.refresh_from_db()
    return JsonResponse({'success': True, 'data': post_to_dict(post)})


@csrf_exempt
@require_http_methods(['POST'])
def publish_post(request, post_id):
    """Publish a scheduled post immediately to its platforms.

    This is a synchronous polling-based publish. For each platform:
    1. Check that the client has a valid connection
    2. Call the platform API
    3. Update ScheduledPlatform status
    4. Return result

    If any platform fails, the others still get published. Post status = worst platform status.
    """
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        post = ScheduledPost.objects.prefetch_related('platform_posts').get(
            id=post_id, client=client
        )
    except ScheduledPost.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)

    from core.platform_api import publish_to_platform

    results = {}
    worst_status = 'posted'

    for sp in post.platform_posts.all():
        if sp.status == 'posted':
            results[sp.platform] = {
                'status': 'posted',
                'platform_post_id': sp.platform_post_id,
                'message': 'Already posted'
            }
            continue

        try:
            result = publish_to_platform(
                client=client,
                platform=sp.platform,
                content=post.content,
                media_urls=post.media_urls,
                link_url=post.link_url,
            )
            if result.get('success'):
                sp.status = 'posted'
                sp.platform_post_id = result.get('platform_post_id', '')
                sp.error_message = ''
            else:
                sp.status = 'failed'
                sp.error_message = result.get('error', 'Unknown error')
                worst_status = 'failed'
            results[sp.platform] = result

        except Exception as e:
            sp.status = 'failed'
            sp.error_message = str(e)
            worst_status = 'failed'
            results[sp.platform] = {'success': False, 'error': str(e)}

        sp.save()

    # Update post overall status
    if worst_status == 'failed':
        post.status = 'failed'
    elif all(r.get('status') == 'posted' for r in results.values()):
        post.status = 'published'
    else:
        post.status = 'scheduled'
    post.save()

    return JsonResponse({
        'success': worst_status != 'failed',
        'data': {
            'post': post_to_dict(post),
            'platform_results': results,
        }
    })


@csrf_exempt
@require_http_methods(['GET'])
def calendar_view(request):
    """Get posts for calendar view.

    Query params:
        year: int (required)
        month: int 1-12 (required)
        platform: filter by platform (optional)
    """
    client = get_client(request)
    if not client:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        year = int(request.GET.get('year', timezone.now().year))
        month = int(request.GET.get('month', timezone.now().month))
    except ValueError:
        return JsonResponse({'error': 'year and month are required'}, status=400)

    from calendar import monthrange
    _, last_day = monthrange(year, month)
    start_date = timezone.make_aware(datetime(year, month, 1))
    end_date = timezone.make_aware(datetime(year, month, last_day, 23, 59, 59))

    queryset = ScheduledPost.objects.filter(
        client=client,
        scheduled_time__gte=start_date,
        scheduled_time__lte=end_date,
    ).prefetch_related('platform_posts')

    platform = request.GET.get('platform')
    if platform:
        queryset = queryset.filter(platform_posts__platform=platform)

    posts_by_day = {}
    for post in queryset:
        day = post.scheduled_time.day
        if day not in posts_by_day:
            posts_by_day[day] = []
        posts_by_day[day].append(post_to_dict(post, include_platforms=True))

    # Fill in all days of the month
    calendar_data = []
    for day in range(1, last_day + 1):
        calendar_data.append({
            'day': day,
            'posts': posts_by_day.get(day, [])
        })

    return JsonResponse({
        'success': True,
        'data': {
            'year': year,
            'month': month,
            'days': calendar_data,
        }
    })


def post_to_dict(post, include_platforms=False):
    """Convert a ScheduledPost to a dict for JSON serialization"""
    data = {
        'id': post.id,
        'content': post.content,
        'media_urls': post.media_urls,
        'link_url': post.link_url,
        'scheduled_time': post.scheduled_time.isoformat() if post.scheduled_time else None,
        'status': post.status,
        'created_at': post.created_at.isoformat() if post.created_at else None,
        'updated_at': post.updated_at.isoformat() if post.updated_at else None,
    }
    if include_platforms:
        data['platforms'] = [
            {
                'platform': sp.platform,
                'status': sp.status,
                'platform_post_id': sp.platform_post_id,
                'error_message': sp.error_message,
            }
            for sp in post.platform_posts.all()
        ]
    return data
