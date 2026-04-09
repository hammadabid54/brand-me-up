"""
Ad platform API services: Meta Ads and Google Ads.
Each service handles OAuth, API calls, and data normalization.
"""
import logging
import time
from datetime import datetime, timedelta
from django.conf import settings

logger = logging.getLogger(__name__)


# Simple in-memory cache: key -> (expires_at, data)
_cache = {}
_CACHE_TTL = 300  # 5 minutes


def _get_cached(key):
    """Get cached value if not expired"""
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, data = entry
    if time.time() > expires_at:
        del _cache[key]
        return None
    return data


def _set_cached(key, data, ttl=_CACHE_TTL):
    """Store value in cache with TTL"""
    _cache[key] = (time.time() + ttl, data)


class AdServiceBase:
    """Base class for ad platform services"""

    def __init__(self, credentials):
        self.credentials = credentials

    def get_data(self, date_range='7d'):
        """Fetch ad data for the specified date range. Override in subclass."""
        raise NotImplementedError

    def _parse_date_range(self, date_range):
        """Convert shorthand date range to start/end dates"""
        now = datetime.utcnow()
        end = now.strftime('%Y-%m-%d')
        if date_range == '7d':
            start = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        elif date_range == '28d':
            start = (now - timedelta(days=28)).strftime('%Y-%m-%d')
        elif date_range == '30d':
            start = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        elif date_range == '90d':
            start = (now - timedelta(days=90)).strftime('%Y-%m-%d')
        else:
            start = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        return start, end


class MetaAdsService(AdServiceBase):
    """Meta Ads Manager via Facebook Graph API"""

    BASE_URL = 'https://graph.facebook.com/v19.0'

    def __init__(self, credentials):
        super().__init__(credentials)
        self.access_token = credentials.get('access_token')

    def _get(self, endpoint, params=None):
        """Make a GET request to Meta Graph API"""
        import requests
        url = f'{self.BASE_URL}/{endpoint}'
        params = params or {}
        params['access_token'] = self.access_token
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise AdServiceError('Meta API timeout')
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise AdServiceError('Meta token expired')
            raise AdServiceError(f'Meta API error: {e}')
        except requests.exceptions.RequestException as e:
            raise AdServiceError(f'Meta API request failed: {e}')

    def get_data(self, date_range='7d'):
        """Get Meta Ads overview data"""
        start, end = self._parse_date_range(date_range)
        cache_key = f'meta_ads_{self._get_ad_account_id()}_{date_range}'
        cached = _get_cached(cache_key)
        if cached:
            return cached

        try:
            account_id = self._get_ad_account_id()
            if not account_id:
                return {'error': 'No ad account found'}

            data = {
                'account_id': account_id,
                'date_range': {'start': start, 'end': end},
                'campaigns': self._get_campaigns(account_id, start, end),
                'adsets': self._get_adsets(account_id, start, end),
                'ads': self._get_ads(account_id, start, end),
                'overview': self._get_overview(account_id, start, end),
            }
            result = {'success': True, 'data': data}
            _set_cached(cache_key, result)
            return result
        except AdServiceError as e:
            logger.error(f'MetaAdsService error: {e}')
            return {'error': str(e)}

    def _get_ad_account_id(self):
        """Get the client's ad account ID"""
        me = self._get('me/accounts')
        accounts = me.get('data', [])
        if accounts:
            return accounts[0]['id']
        return None

    def _get_overview(self, account_id, start, end):
        """Get account-level overview stats"""
        fields = [
            'impressions',
            'reach',
            'frequency',
            'clicks',
            'ctr',
            'cpc',
            'spend',
            'actions',
            'action_results',
            'cost_per_action_type',
        ]
        params = {
            'fields': ','.join(fields),
            'time_range': f'{{"since":"{start}","until":"{end}"}}',
            'level': 'account',
        }
        result = self._get(f'{account_id}/insights', params)
        return result.get('data', [{}])[0] if result.get('data') else {}

    def _get_campaigns(self, account_id, start, end):
        """Get campaign-level performance"""
        fields = [
            'id', 'name', 'status', 'objective',
            'impressions', 'clicks', 'ctr', 'cpc', 'spend',
            'actions', 'action_results',
        ]
        params = {
            'fields': ','.join(fields),
            'time_range': f'{{"since":"{start}","until":"{end}"}}',
            'level': 'campaign',
            'limit': 50,
        }
        result = self._get(f'{account_id}/insights', params)
        return result.get('data', [])

    def _get_adsets(self, account_id, start, end):
        """Get adset-level performance"""
        fields = [
            'id', 'name', 'status',
            'impressions', 'clicks', 'ctr', 'cpc', 'spend',
            'targeting',
        ]
        params = {
            'fields': ','.join(fields),
            'time_range': f'{{"since":"{start}","until":"{end}"}}',
            'level': 'adset',
            'limit': 100,
        }
        result = self._get(f'{account_id}/insights', params)
        return result.get('data', [])

    def _get_ads(self, account_id, start, end):
        """Get ad-level performance"""
        fields = [
            'id', 'name', 'status',
            'creative', 'impressions', 'clicks', 'ctr', 'spend',
        ]
        params = {
            'fields': ','.join(fields),
            'time_range': f'{{"since":"{start}","until":"{end}"}}',
            'level': 'ad',
            'limit': 100,
        }
        result = self._get(f'{account_id}/insights', params)
        return result.get('data', [])


class GoogleAdsService(AdServiceBase):
    """Google Ads via Google Ads API"""

    def __init__(self, credentials):
        super().__init__(credentials)
        self.access_token = credentials.get('access_token')
        self.refresh_token = credentials.get('refresh_token')
        self.client_id = credentials.get('client_id')
        self.client_secret = credentials.get('client_secret')
        self.customer_id = credentials.get('customer_id')  # Required: client's Google Ads customer ID

    def _build_credentials(self):
        """Build google-auth Credentials object"""
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=['https://www.googleapis.com/auth/adwords.read']
        )

    def get_data(self, date_range='7d'):
        """Get Google Ads data"""
        start, end = self._parse_date_range(date_range)
        if not self.customer_id:
            return {'error': 'Google Ads customer_id not configured'}

        cache_key = f'google_ads_{self.customer_id}_{date_range}'
        cached = _get_cached(cache_key)
        if cached:
            return cached

        try:
            import requests
            creds = self._build_credentials()
            access_token = creds.token

            headers = {
                'Authorization': f'Bearer {access_token}',
                'developer-token': settings.GOOGLE_ADS_DEVELOPER_TOKEN if hasattr(settings, 'GOOGLE_ADS_DEVELOPER_TOKEN') else '',
                'User-Agent': 'OmniPathMarketing/1.0',
            }

            # GAQL query for campaign performance
            query = f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    campaign.budget.amount.micro_amount,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.ctr,
                    metrics.average_cpc,
                    metrics.spend,
                    metrics.conversions
                FROM campaign
                WHERE campaign.status != 'REMOVED'
                AND segments.date BETWEEN '{start}' AND '{end}'
                ORDER BY metrics.impressions DESC
                LIMIT 100
            """

            body = {
                'customerId': self.customer_id,
                'query': query,
            }

            response = requests.post(
                f'https://googleads.googleapis.com/v17/customers/{self.customer_id}/googleAds:search',
                headers=headers,
                json=body,
                timeout=30
            )

            if response.status_code == 401:
                return {'error': 'Google Ads token expired'}
            if response.status_code != 200:
                return {'error': f'Google Ads API error: {response.status_code}'}

            result = response.json()
            campaigns = []
            for row in result.get('results', []):
                campaign = row.get('campaign', {})
                metrics = row.get('metrics', {})
                campaigns.append({
                    'id': campaign.get('id', {}).get('value'),
                    'name': campaign.get('name', {}).get('value'),
                    'status': campaign.get('status', {}).get('status'),
                    'budget_micros': campaign.get('budget', {}).get('amount', {}).get('microAmount', 0),
                    'impressions': metrics.get('impressions', {}).get('value', 0),
                    'clicks': metrics.get('clicks', {}).get('value', 0),
                    'ctr': metrics.get('ctr', {}).get('value', 0),
                    'cpc': metrics.get('averageCpc', {}).get('value', 0),
                    'spend': metrics.get('spend', {}).get('value', 0) / 1_000_000,  # Micros to dollars
                    'conversions': metrics.get('conversions', {}).get('value', 0),
                })

            return {
                'success': True,
                'data': {
                    'customer_id': self.customer_id,
                    'date_range': {'start': start, 'end': end},
                    'campaigns': campaigns,
                    'totals': self._calculate_totals(campaigns),
                }
            }

        except Exception as e:
            logger.error(f'GoogleAdsService error: {e}')
            return {'error': str(e)}

    def _calculate_totals(self, campaigns):
        """Sum metrics across all campaigns"""
        return {
            'impressions': sum(c.get('impressions', 0) for c in campaigns),
            'clicks': sum(c.get('clicks', 0) for c in campaigns),
            'spend': sum(c.get('spend', 0) for c in campaigns),
            'conversions': sum(c.get('conversions', 0) for c in campaigns),
        }


class AdServiceError(Exception):
    """Custom exception for ad service errors"""
    pass
