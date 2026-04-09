"""
Platform API clients for social media posting.
Each platform has its own OAuth flow and posting API.
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PlatformAPIError(Exception):
    """Base exception for platform API errors"""
    pass


class TokenExpiredError(PlatformAPIError):
    """Raised when the platform OAuth token has expired"""
    pass


def get_platform_credentials(client, platform):
    """Get stored credentials for a platform from ClientConnection.

    Returns a dict with access_token and related fields, or None if not connected.
    """
    from core.models import ClientConnection

    # Map platform names to service names in ClientConnection
    service_map = {
        'facebook': 'meta_facebook',
        'instagram': 'meta_instagram',
        'linkedin': 'linkedin',
        'pinterest': 'pinterest',
    }
    service = service_map.get(platform)
    if not service:
        return None

    try:
        conn = ClientConnection.objects.get(client=client, service=service)
        if not conn.is_connected or not conn.access_token:
            return None
        return {
            'access_token': conn.access_token,
            'refresh_token': conn.refresh_token,
            'token_uri': conn.token_uri if hasattr(conn, 'token_uri') else None,
            'client_id': conn.client_id if hasattr(conn, 'client_id') else None,
            'client_secret': conn.client_secret if hasattr(conn, 'client_secret') else None,
        }
    except ClientConnection.DoesNotExist:
        return None


def publish_to_platform(client, platform, content, media_urls=None, link_url=None):
    """Publish a post to the specified platform.

    Returns dict: {'success': bool, 'platform_post_id': str, 'error': str}
    """
    dispatch = {
        'facebook': _publish_facebook,
        'instagram': _publish_instagram,
        'linkedin': _publish_linkedin,
        'pinterest': _publish_pinterest,
    }
    func = dispatch.get(platform)
    if not func:
        return {'success': False, 'error': f'Unknown platform: {platform}'}

    try:
        return func(client, content, media_urls or [], link_url or '')
    except TokenExpiredError:
        return {'success': False, 'error': 'Platform connection expired. Please reconnect.'}
    except PlatformAPIError as e:
        return {'success': False, 'error': str(e)}
    except Exception as e:
        logger.error(f'publish_to_platform({platform}) unexpected error: {e}')
        return {'success': False, 'error': f'Unexpected error: {e}'}


def _publish_facebook(client, content, media_urls, link_url):
    """Publish to Facebook Page via Graph API"""
    credentials = get_platform_credentials(client, 'facebook')
    if not credentials:
        raise PlatformAPIError('Facebook not connected')

    access_token = credentials['access_token']

    # Get the user's Pages
    pages_url = 'https://graph.facebook.com/v19.0/me/accounts'
    pages_resp = requests.get(pages_url, params={'access_token': access_token}, timeout=30)
    if pages_resp.status_code == 401:
        raise TokenExpiredError('Facebook token expired')
    pages_data = pages_resp.json()
    pages = pages_data.get('data', [])
    if not pages:
        raise PlatformAPIError('No Facebook Pages found')

    page_token = pages[0]['access_token']
    page_id = pages[0]['id']

    # Build media attachments first if media exists
    attached_media = []
    if media_urls:
        for url in media_urls:
            photo_resp = requests.post(
                f'https://graph.facebook.com/v19.0/{page_id}/photos',
                data={'url': url, 'published': False, 'access_token': page_token},
                timeout=30
            )
            if photo_resp.ok:
                attached_media.append({'media_id': photo_resp.json().get('id')})

    # Build the post
    post_data = {
        'message': content,
        'access_token': page_token,
    }
    if link_url:
        post_data['link'] = link_url
    if attached_media:
        # For photos, use the photos endpoint instead
        if len(attached_media) == 1:
            post_data['attached_media'] = [attached_media[0]]
        # Multi-photo posts need the multi-photo endpoint
        attached_media_data = [{'media_id': m['media_id']} for m in attached_media]

    endpoint = f'https://graph.facebook.com/v19.0/{page_id}/feed'
    resp = requests.post(endpoint, data=post_data, timeout=30)

    if not resp.ok:
        resp_data = resp.json()
        err = resp_data.get('error', {})
        raise PlatformAPIError(err.get('message', 'Facebook post failed'))

    result = resp.json()
    return {
        'success': True,
        'platform_post_id': result.get('id', ''),
        'post_url': f"https://facebook.com/{result.get('id')}",
    }


def _publish_instagram(client, content, media_urls, link_url):
    """Publish to Instagram via Graph API (requires Facebook Page linked to Instagram)"""
    credentials = get_platform_credentials(client, 'instagram')
    if not credentials:
        raise PlatformAPIError('Instagram not connected')

    access_token = credentials['access_token']

    # Get the Instagram business account linked to the Facebook Page
    me_url = 'https://graph.facebook.com/v19.0/me'
    me_resp = requests.get(me_url, params={
        'fields': 'instagram_business_account',
        'access_token': access_token
    }, timeout=30)
    me_data = me_resp.json()

    instagram_account_id = me_data.get('instagram_business_account', {}).get('id')
    if not instagram_account_id:
        raise PlatformAPIError('No Instagram Business account linked')

    # Create media item (image container)
    media_data = {
        'caption': content,
        'access_token': access_token,
    }
    if media_urls:
        media_data['image_url'] = media_urls[0]
    if link_url:
        media_data['link'] = link_url

    media_resp = requests.post(
        f'https://graph.facebook.com/v19.0/{instagram_account_id}/media',
        data=media_data,
        timeout=30
    )
    if not media_resp.ok:
        raise PlatformAPIError(f'Instagram media creation failed: {media_resp.text}')

    creation_id = media_resp.json().get('id')

    # Publish the media item
    publish_resp = requests.post(
        f'https://graph.facebook.com/v19.0/{instagram_account_id}/media_publish',
        data={'creation_id': creation_id, 'access_token': access_token},
        timeout=30
    )
    if not publish_resp.ok:
        raise PlatformAPIError(f'Instagram publish failed: {publish_resp.text}')

    result = publish_resp.json()
    return {
        'success': True,
        'platform_post_id': result.get('id', ''),
    }


def _publish_linkedin(client, content, media_urls, link_url):
    """Publish to LinkedIn via LinkedIn API"""
    credentials = get_platform_credentials(client, 'linkedin')
    if not credentials:
        raise PlatformAPIError('LinkedIn not connected')

    access_token = credentials['access_token']

    # Get the user's LinkedIn page (organization)
    user_url = 'https://api.linkedin.com/v2/userinfo'
    user_resp = requests.get(user_url, headers={'Authorization': f'Bearer {access_token}'}, timeout=30)
    if user_resp.status_code == 401:
        raise TokenExpiredError('LinkedIn token expired')
    user_data = user_resp.json()
    person_id = user_data.get('sub')

    # For personal posts, use ugcPosts API
    # For company page posts, use organization posts API (requires organization ID)
    post_url = 'https://api.linkedin.com/v2/ugcPosts'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Method': 'POST',
    }
    body = {
        'author': f'urn:li:person:{person_id}',
        'lifecycleState': 'PUBLISHED',
        'specificContent': {
            'com.linkedin.ugc.ShareContent': {
                'shareCommentary': {'text': content},
                'shareMediaCategory': 'NONE',
            }
        },
        'visibility': {
            'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'
        }
    }
    if link_url:
        body['specificContent']['com.linkedin.ugc.ShareContent']['shareMediaCategory'] = 'ARTICLE'
        body['specificContent']['com.linkedin.ugc.ShareContent']['media'] = [{
            'mediaMessage': {'text': link_url},
            'status': 'READY',
        }]

    resp = requests.post(post_url, headers=headers, json=body, timeout=30)
    if not resp.ok:
        raise PlatformAPIError(f'LinkedIn post failed: {resp.text}')

    result = resp.json()
    return {
        'success': True,
        'platform_post_id': result.get('id', ''),
    }


def _publish_pinterest(client, content, media_urls, link_url):
    """Publish to Pinterest via Pinterest API"""
    credentials = get_platform_credentials(client, 'pinterest')
    if not credentials:
        raise PlatformAPIError('Pinterest not connected')

    access_token = credentials['access_token']

    # Get the user's Pinterest boards to find where to post
    boards_url = 'https://api.pinterest.com/v5/boards'
    boards_resp = requests.get(boards_url, headers={'Authorization': f'Bearer {access_token}'}, timeout=30)
    if boards_resp.status_code == 401:
        raise TokenExpiredError('Pinterest token expired')
    if not boards_resp.ok:
        raise PlatformAPIError(f'Pinterest boards fetch failed: {boards_resp.text}')

    boards_data = boards_resp.json()
    boards = boards_data.get('items', [])
    if not boards:
        raise PlatformAPIError('No Pinterest boards found for this account')

    board_id = boards[0]['id']

    # Create a pin on the first board
    pin_url = 'https://api.pinterest.com/v5/pins'
    pin_data = {
        'board_id': board_id,
        'note': content,
        'link': link_url or '',
    }
    if media_urls:
        pin_data['media_url'] = media_urls[0]

    pin_resp = requests.post(pin_url, headers={'Authorization': f'Bearer {access_token}'}, json=pin_data, timeout=30)
    if not pin_resp.ok:
        raise PlatformAPIError(f'Pinterest pin creation failed: {pin_resp.text}')

    result = pin_resp.json()
    return {
        'success': True,
        'platform_post_id': result.get('id', ''),
        'post_url': f"https://pinterest.com/pin/{result.get('id', '')}",
    }
