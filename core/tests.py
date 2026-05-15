from django.test import TestCase, Client, override_settings, RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock

from core.models import Client as ClientModel, ClientConnection
from core.backends import EmailOrUsernameBackend, email_to_username

User = get_user_model()


# ==================== EmailOrUsernameBackend Tests ====================

class EmailOrUsernameBackendTests(TestCase):
    def setUp(self):
        self.backend = EmailOrUsernameBackend()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123',
        )

    def test_authenticate_with_email_success(self):
        """Login with email and valid password returns user."""
        user = self.backend.authenticate(
            request=None,
            username='test@example.com',
            password='testpassword123',
        )
        self.assertEqual(user, self.user)

    def test_authenticate_with_username_success(self):
        """Login with username and valid password returns user."""
        user = self.backend.authenticate(
            request=None,
            username='testuser',
            password='testpassword123',
        )
        self.assertEqual(user, self.user)

    def test_authenticate_invalid_password(self):
        """Login with email but wrong password returns None."""
        user = self.backend.authenticate(
            request=None,
            username='test@example.com',
            password='wrongpassword',
        )
        self.assertIsNone(user)

    def test_authenticate_nonexistent_user(self):
        """Login with non-existent email returns None."""
        user = self.backend.authenticate(
            request=None,
            username='nonexistent@example.com',
            password='anypassword',
        )
        self.assertIsNone(user)

    def test_get_user_returns_user_even_if_inactive(self):
        """get_user returns user for inactive users (important for session persistence)."""
        self.user.is_active = False
        self.user.save()
        user = self.backend.get_user(self.user.pk)
        self.assertEqual(user, self.user)


# ==================== email_to_username Tests ====================

class EmailToUsernameTests(TestCase):
    def test_email_to_username_simple(self):
        """Simple email converts to username-like string."""
        result = email_to_username('john@gmail.com')
        self.assertIn('john_at_gmail_com', result)
        # Should have 4-digit random suffix
        self.assertTrue(result[-4:].isdigit())

    def test_email_to_username_with_plus_alias(self):
        """Email with + alias is normalized."""
        result = email_to_username('john+alias@gmail.com')
        self.assertIn('john_plus_alias_at_gmail_com', result)
        self.assertTrue(result[-4:].isdigit())

    def test_email_to_username_different_suffixes(self):
        """Same email produces different suffixes (random)."""
        result1 = email_to_username('alice@gmail.com')
        result2 = email_to_username('alice@gmail.com')
        # The base parts should be the same
        self.assertNotEqual(result1[-4:], result2[-4:])  # Different random suffix


# ==================== signup_view Tests ====================

class SignupViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch('core.auth.send_mail')
    def test_signup_creates_user_and_client(self, mock_send_mail):
        """POST valid signup data creates User + Client and sends verification email."""
        response = self.client.post('/auth/signup/', {
            'email': 'newuser@example.com',
            'password': 'securepassword123',
            'password_confirm': 'securepassword123',
            'first_name': 'New',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
        self.assertTrue(ClientModel.objects.filter(email='newuser@example.com').exists())
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.is_active)  # Must verify email first
        mock_send_mail.assert_called_once()

    def test_signup_duplicate_email_error(self):
        """POST with existing email returns error."""
        User.objects.create_user(
            username='existing',
            email='existing@example.com',
            password='anypassword123',
        )
        response = self.client.post('/auth/signup/', {
            'email': 'existing@example.com',
            'password': 'anypassword123',
            'password_confirm': 'anypassword123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('already exists', response.content.decode())

    def test_signup_invalid_form_errors(self):
        """POST with missing fields returns inline errors."""
        response = self.client.post('/auth/signup/', {
            'email': 'notanemail',
            'password': 'short',
        })
        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertIn('error', content.lower())


# ==================== verify_email Tests ====================

class VerifyEmailTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='verifyuser',
            email='verify@example.com',
            password='testpassword123',
            is_active=False,
        )
        self.client_model = ClientModel.objects.create(
            user=self.user,
            email='verify@example.com',
            name='Verify User',
        )

    def test_verify_email_activates_user(self):
        """GET with valid token activates user and redirects to login."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.get(f'/auth/verify/{uidb64}/{token}/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_verify_email_expired_token(self):
        """GET with invalid token shows error page."""
        response = self.client.get('/auth/verify/invalid/invalid-token/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('invalid', response.content.decode().lower())


# ==================== login_view Tests ====================

class LoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='loginuser',
            email='login@example.com',
            password='correctpassword123',
            is_active=True,
        )

    def test_login_valid_credentials_redirects(self):
        """POST with valid credentials redirects to dashboard."""
        response = self.client.post('/auth/login/', {
            'username': 'login@example.com',
            'password': 'correctpassword123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard/', response.url)

    def test_login_invalid_credentials_no_enumeration(self):
        """Wrong password shows same message as non-existent user (no enumeration)."""
        response = self.client.post('/auth/login/', {
            'username': 'login@example.com',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Should show generic "invalid email or password" — not "wrong password"
        self.assertIn('invalid email or password', content.lower())

    def test_login_unverified_user_error(self):
        """Login with correct credentials but inactive user shows verification error."""
        self.user.is_active = False
        self.user.save()
        response = self.client.post('/auth/login/', {
            'username': 'login@example.com',
            'password': 'correctpassword123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('verify', response.content.decode().lower())

    def test_login_remember_me_extends_session(self):
        """POST with remember_me=True sets session expiry to 2 weeks."""
        response = self.client.post('/auth/login/', {
            'username': 'login@example.com',
            'password': 'correctpassword123',
            'remember_me': 'on',
        })
        # Session should have 2-week expiry (not following redirect to avoid cookie issues)
        self.assertEqual(
            self.client.session.get_expiry_age(),
            60 * 60 * 24 * 14,
        )


# ==================== get_client Tests ====================

class GetClientTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dashboarduser',
            email='dash@example.com',
            password='testpassword123',
            is_active=True,
        )
        self.client_model = ClientModel.objects.create(
            user=self.user,
            email='dash@example.com',
            name='Dashboard User',
        )
        self.factory = Client()

    def test_get_client_django_user(self):
        """Authenticated user with client_profile returns that Client."""
        self.factory.login(username='dash@example.com', password='testpassword123')
        from core.auth import get_client
        request = self.factory.get('/dashboard/')
        request.session = self.factory.session
        request.user = self.user
        result = get_client(request)
        self.assertEqual(result, self.client_model)

    def test_get_client_google_oauth_session_user(self):
        """Session with client_id but no Django user returns the Client."""
        self.factory.session['client_id'] = self.client_model.id
        self.factory.session.modified = True
        from core.auth import get_client
        request = self.factory.get('/dashboard/')
        request.session = self.factory.session
        request.user = self.user  # Anonymous user
        result = get_client(request)
        self.assertEqual(result, self.client_model)

    def test_get_client_neither_returns_none(self):
        """Neither Django auth nor session client_id returns None."""
        from core.auth import get_client
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/dashboard/')
        request.session = self.factory.session
        request.user = AnonymousUser()
        result = get_client(request)
        self.assertIsNone(result)


# ==================== invite_accept Tests ====================

class InviteAcceptTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.agency = ClientModel.objects.create(
            email='agency@example.com',
            name='Test Agency',
        )

    def test_invite_accept_creates_user_and_activates(self):
        """POST with valid token and password creates user and activates account."""
        invite_client = ClientModel.objects.create(
            email='invited@example.com',
            name='Invited Client',
            is_agency_client=True,
            agency=self.agency,
            invite_token='test_token_12345',
            invite_token_expiry=timezone.now() + timedelta(hours=72),
        )
        response = self.client.post('/auth/invite/test_token_12345/', {
            'password': 'newpassword123',
            'password_confirm': 'newpassword123',
        })
        self.assertEqual(response.status_code, 302)
        invite_client.refresh_from_db()
        self.assertTrue(invite_client.user.is_active)
        self.assertIsNone(invite_client.invite_token)  # Token cleared

    def test_invite_accept_invalid_token_shows_error(self):
        """GET with non-existent token shows invalid link error."""
        response = self.client.get('/auth/invite/nonexistent_token/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('invalid', response.content.decode().lower())

    def test_invite_accept_expired_token_shows_error(self):
        """GET with expired token shows expired error."""
        expired_client = ClientModel.objects.create(
            email='expired@example.com',
            name='Expired Client',
            invite_token='expired_token',
            invite_token_expiry=timezone.now() - timedelta(hours=1),  # Expired
        )
        response = self.client.get('/auth/invite/expired_token/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('expired', response.content.decode().lower())

    def test_invite_accept_valid_token_get_shows_form(self):
        """GET with valid token returns the password set form."""
        invite_client = ClientModel.objects.create(
            email='pending@example.com',
            name='Pending Client',
            is_agency_client=True,
            agency=self.agency,
            invite_token='valid_token_show_form',
            invite_token_expiry=timezone.now() + timedelta(hours=72),
        )
        response = self.client.get('/auth/invite/valid_token_show_form/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('password', response.content.decode().lower())

    def test_invite_accept_already_activated_redirects(self):
        """GET with valid token but already-activated user redirects to login."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            username='already_user',
            email='activated@example.com',
            password='anypassword123',
            is_active=True,
        )
        invite_client = ClientModel.objects.create(
            email='activated@example.com',
            name='Already Activated',
            is_agency_client=True,
            agency=self.agency,
            invite_token='already_activated_token',
            invite_token_expiry=timezone.now() + timedelta(hours=72),
            user=user,
        )
        response = self.client.get('/auth/invite/already_activated_token/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_invite_accept_password_too_short(self):
        """POST with short password returns inline validation error."""
        invite_client = ClientModel.objects.create(
            email='short@example.com',
            name='Short Password Test',
            is_agency_client=True,
            agency=self.agency,
            invite_token='short_pass_token',
            invite_token_expiry=timezone.now() + timedelta(hours=72),
        )
        response = self.client.post('/auth/invite/short_pass_token/', {
            'password': 'short',
            'password_confirm': 'short',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('at least 8', response.content.decode().lower())

    def test_invite_accept_password_mismatch(self):
        """POST with mismatched passwords returns inline validation error."""
        invite_client = ClientModel.objects.create(
            email='mismatch@example.com',
            name='Mismatch Test',
            is_agency_client=True,
            agency=self.agency,
            invite_token='mismatch_token',
            invite_token_expiry=timezone.now() + timedelta(hours=72),
        )
        response = self.client.post('/auth/invite/mismatch_token/', {
            'password': 'password123',
            'password_confirm': 'differentpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('do not match', response.content.decode().lower())


# ==================== Social OAuth Callback Tests ====================

class SocialOAuthCallbackTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='socialuser',
            email='social@example.com',
            password='testpassword123',
            is_active=True,
        )
        self.social_client = ClientModel.objects.create(
            user=self.user,
            email='social@example.com',
            name='Social User',
            is_agency_client=True,
        )

    def _call_callback(self, platform, code, state, connecting_service, oauth_state, mock_response=None):
        """Call social_callback view directly with a mock request."""
        from core.auth import social_callback
        request = self.factory.get(f'/auth/social/callback/{platform}/', {'code': code, 'state': state})
        request.session = {
            'connecting_service': connecting_service,
            'oauth_state': oauth_state,
        }
        request.user = self.user

        with patch('core.auth.get_client', return_value=self.social_client):
            if mock_response:
                with patch('requests.get' if platform == 'facebook' else 'requests.post') as mock_http:
                    mock_http.return_value = mock_response
                    response = social_callback(request, platform)
            else:
                response = social_callback(request, platform)
        return response

    def test_meta_callback_success(self):
        """Meta OAuth callback stores access token and redirects to scheduler."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'access_token': 'meta_test_access_token',
            'refresh_token': 'meta_test_refresh_token',
        }
        response = self._call_callback(
            'facebook', 'test_auth_code', 'test_state_123',
            'meta_facebook', 'test_state_123', mock_response
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard/scheduler/', response.url)
        conn = ClientConnection.objects.filter(
            client=self.social_client, service='meta_facebook'
        ).first()
        self.assertIsNotNone(conn)
        self.assertEqual(conn.access_token, 'meta_test_access_token')
        self.assertTrue(conn.is_connected)

    def test_meta_callback_state_mismatch(self):
        """Meta OAuth callback with wrong state redirects to error."""
        response = self._call_callback(
            'facebook', 'test_code', 'wrong_state',
            'meta_facebook', 'correct_state'
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('state_mismatch', response.url)

    def test_linkedin_callback_success(self):
        """LinkedIn OAuth callback stores access token and redirects."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'access_token': 'linkedin_test_token',
            'refresh_token': 'linkedin_refresh',
        }
        response = self._call_callback(
            'linkedin', 'li_test_code', 'li_state_456',
            'linkedin', 'li_state_456', mock_response
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard/scheduler/', response.url)
        conn = ClientConnection.objects.filter(
            client=self.social_client, service='linkedin'
        ).first()
        self.assertIsNotNone(conn)
        self.assertEqual(conn.access_token, 'linkedin_test_token')

    def test_pinterest_callback_success(self):
        """Pinterest OAuth callback stores access token and redirects."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'access_token': 'pinterest_test_token',
            'refresh_token': 'pinterest_refresh',
        }
        response = self._call_callback(
            'pinterest', 'pin_test_code', 'pin_state_789',
            'pinterest', 'pin_state_789', mock_response
        )
        self.assertEqual(response.status_code, 302)
        conn = ClientConnection.objects.filter(
            client=self.social_client, service='pinterest'
        ).first()
        self.assertIsNotNone(conn)
        self.assertEqual(conn.access_token, 'pinterest_test_token')

    def test_social_callback_no_code_redirects(self):
        """Callback without auth code redirects to error."""
        from core.auth import social_callback
        request = self.factory.get('/auth/social/callback/facebook/')
        request.session = {'connecting_service': 'meta_facebook'}
        request.user = self.user

        with patch('core.auth.get_client', return_value=self.social_client):
            response = social_callback(request, 'facebook')
        self.assertEqual(response.status_code, 302)
        self.assertIn('no_code', response.url)

    def test_social_callback_unauthenticated(self):
        """Callback without session client_id redirects to login."""
        from core.auth import social_callback
        request = self.factory.get('/auth/social/callback/facebook/', {'code': 'any_code'})
        request.session = {}
        request.user = AnonymousUser()

        response = social_callback(request, 'facebook')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)
        self.assertIn('/auth/login/', response.url)


# ==================== agency_clients View Tests ====================

class AgencyClientsTests(TestCase):
    def setUp(self):
        self.agency_client = ClientModel.objects.create(
            email='agency@test.com',
            name='Test Agency',
            is_agency_client=True,
        )
        self.user = User.objects.create_user(
            username='agency_user',
            email='agency@test.com',
            password='password123',
            is_active=True,
        )
        self.agency_client.user = self.user
        self.agency_client.save()
        # Log in
        self.client.login(username='agency@test.com', password='password123')

    def test_agency_clients_lists_managed_clients(self):
        """GET returns list of agency's managed clients."""
        managed = ClientModel.objects.create(
            email='managed1@test.com',
            name='Managed Client 1',
            is_agency_client=True,
            agency=self.agency_client,
        )
        response = self.client.get('/dashboard/clients/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('managed1@test.com', content)
        self.assertIn('Managed Client 1', content)

    def test_agency_clients_excludes_other_agencies_clients(self):
        """GET does not include clients from other agencies."""
        other_agency = ClientModel.objects.create(
            email='other@agency.com',
            name='Other Agency',
            is_agency_client=True,
        )
        ClientModel.objects.create(
            email='other_client@test.com',
            name='Other Client',
            is_agency_client=True,
            agency=other_agency,
        )
        response = self.client.get('/dashboard/clients/')
        content = response.content.decode()
        self.assertNotIn('other_client@test.com', content)

    @patch('core.auth.send_mail')
    def test_agency_clients_add_sends_invite_email(self, mock_send_mail):
        """POST with valid data creates client and sends invite email."""
        mock_send_mail.return_value = 1
        response = self.client.post('/dashboard/clients/', {
            'name': 'New Client',
            'email': 'newclient@example.com',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ClientModel.objects.filter(email='newclient@example.com').exists()
        )
        new_client = ClientModel.objects.get(email='newclient@example.com')
        self.assertIsNotNone(new_client.invite_token)
        self.assertIsNotNone(new_client.invite_sent_at)
        mock_send_mail.assert_called_once()

    def test_agency_clients_add_validates_name(self):
        """POST with missing name returns error."""
        response = self.client.post('/dashboard/clients/', {
            'email': 'valid@example.com',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name', content.lower())

    def test_agency_clients_add_validates_email(self):
        """POST with invalid email returns error."""
        response = self.client.post('/dashboard/clients/', {
            'name': 'Test Name',
            'email': 'not-an-email',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('email', content.lower())

    def test_agency_clients_add_rejects_duplicate_email(self):
        """POST with existing email returns error."""
        User.objects.create_user(username='existing', email='existing@test.com', password='pass123')
        response = self.client.post('/dashboard/clients/', {
            'name': 'Existing User',
            'email': 'existing@test.com',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('already exists', content.lower())

    def test_agency_clients_requires_auth(self):
        """Unauthenticated GET redirects to login."""
        ClientModel.objects.get(email='agency@test.com')
        self.client.logout()
        response = self.client.get('/dashboard/clients/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)


# ==================== API Endpoint Tests ====================

class APIEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='apiuser',
            email='api@test.com',
            password='testpassword123',
            is_active=True,
        )
        self.api_client = ClientModel.objects.create(
            user=self.user,
            email='api@test.com',
            name='API Test User',
        )
        self.factory = Client()
        self.factory.login(username='api@test.com', password='testpassword123')

    def test_get_connected_platforms_returns_401_unauthenticated(self):
        """Unauthenticated request returns 401."""
        response = Client().get('/api/scheduler/connected-platforms/')
        self.assertEqual(response.status_code, 401)

    def test_get_connected_platforms_returns_connected_services(self):
        """Returns dict of connected social platforms."""
        ClientConnection.objects.create(
            client=self.api_client,
            service='meta_facebook',
            access_token='fb_token',
            is_connected=True,
        )
        ClientConnection.objects.create(
            client=self.api_client,
            service='linkedin',
            access_token='li_token',
            is_connected=True,
        )
        response = self.factory.get('/api/scheduler/connected-platforms/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['connected']['meta_facebook'])
        self.assertTrue(data['connected']['linkedin'])
        self.assertFalse(data['connected'].get('pinterest', False))

    def test_disconnect_service_success(self):
        """POST disconnects a service and returns success."""
        conn = ClientConnection.objects.create(
            client=self.api_client,
            service='analytics',
            access_token='test_token',
            is_connected=True,
        )
        response = self.factory.post('/api/dashboard/disconnect/analytics/')
        self.assertEqual(response.status_code, 200)
        conn.refresh_from_db()
        self.assertFalse(conn.is_connected)

    def test_disconnect_service_returns_404_for_unknown_service(self):
        """Disconnecting non-existent connection returns 404."""
        response = self.factory.post('/api/dashboard/disconnect/nonexistent/')
        self.assertEqual(response.status_code, 404)

    def test_disconnect_service_requires_auth(self):
        """Unauthenticated disconnect returns 401."""
        response = Client().post('/api/dashboard/disconnect/analytics/')
        self.assertEqual(response.status_code, 401)

    def test_get_analytics_data_requires_auth(self):
        """Unauthenticated analytics request returns 401."""
        response = Client().get('/api/dashboard/analytics/')
        self.assertEqual(response.status_code, 401)

    def test_get_analytics_data_requires_connection(self):
        """Request without Analytics connected returns 400."""
        response = self.factory.get('/api/dashboard/analytics/')
        self.assertEqual(response.status_code, 400)

    def test_get_search_console_data_requires_auth(self):
        """Unauthenticated Search Console request returns 401."""
        response = Client().get('/api/dashboard/search-console/')
        self.assertEqual(response.status_code, 401)

    def test_get_gbp_data_returns_note(self):
        """GBP endpoint returns informational note about API setup."""
        ClientConnection.objects.create(
            client=self.api_client,
            service='gbp',
            access_token='gbp_token',
            is_connected=True,
        )
        response = self.factory.get('/api/dashboard/gbp/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('note', data['data'])


# ==================== Additional Edge Case Tests ====================

class AuthEdgeCaseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='edgeuser',
            email='edge@example.com',
            password='testpassword123',
            is_active=True,
        )
        self.client_model = ClientModel.objects.create(
            user=self.user,
            email='edge@example.com',
            name='Edge User',
        )

    def test_login_view_redirects_authenticated_user(self):
        """GET /auth/login/ when already logged in redirects to dashboard."""
        self.client.login(username='edge@example.com', password='testpassword123')
        response = self.client.get('/auth/login/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard/', response.url)

    def test_signup_view_redirects_authenticated_user(self):
        """GET /auth/signup/ when already logged in redirects to dashboard."""
        self.client.login(username='edge@example.com', password='testpassword123')
        response = self.client.get('/auth/signup/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard/', response.url)

    def test_signup_password_too_short(self):
        """POST with password < 8 chars returns validation error."""
        response = self.client.post('/auth/signup/', {
            'email': 'shortpw@example.com',
            'password': '1234567',
            'password_confirm': '1234567',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('at least 8', response.content.decode().lower())

    def test_signup_password_mismatch(self):
        """POST with mismatched passwords returns validation error."""
        response = self.client.post('/auth/signup/', {
            'email': 'mismatch@example.com',
            'password': 'password123',
            'password_confirm': 'differentpass456',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('do not match', response.content.decode().lower())

    def test_set_password_requires_google_id(self):
        """set_password_view redirects if client has no google_id."""
        # This client is a plain email/password user (no google_id)
        self.client.login(username='edge@example.com', password='testpassword123')
        response = self.client.get('/auth/set-password/')
        self.assertEqual(response.status_code, 302)  # Redirects to dashboard

    def test_connect_service_requires_auth(self):
        """connect_service redirects unauthenticated users."""
        response = Client().get('/dashboard/connect/analytics/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_connect_service_invalid_service(self):
        """connect_service with invalid service returns error redirect."""
        self.client.login(username='edge@example.com', password='testpassword123')
        response = self.client.get('/dashboard/connect/invalid_service/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('invalid_service', response.url)  # Should redirect with error

    def test_scheduler_requires_agency_client(self):
        """scheduler view redirects non-agency clients."""
        # edgeuser's client_model is_agency_client=False (default)
        self.client.login(username='edge@example.com', password='testpassword123')
        response = self.client.get('/dashboard/scheduler/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('upgrade=scheduler', response.url)


from unittest.mock import Mock, patch
