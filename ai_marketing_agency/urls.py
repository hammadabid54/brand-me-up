"""
URL configuration for ai_marketing_agency project.
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views
from core import auth as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Main Pages
    path('', views.home, name='home'),
    path('services/', views.services, name='services'),
    path('about/', views.about, name='about'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('blog/', views.blog, name='blog'),
    path('contact/', views.contact, name='contact'),

    # SEO Service Pages
    path('services/seo/', views.seo_overview, name='seo_overview'),
    path('services/seo/local-seo/', views.local_seo, name='local_seo'),
    path('services/seo/ecommerce-seo/', views.ecommerce_seo, name='ecommerce_seo'),
    path('services/seo/saas-seo/', views.saas_seo, name='saas_seo'),
    path('services/seo/technical-seo/', views.technical_seo, name='technical_seo'),
    path('services/seo/enterprise-seo/', views.enterprise_seo, name='enterprise_seo'),

    # Social Media Pages
    path('services/social-media/', views.social_media_overview, name='social_media_overview'),
    path('services/social-media/management/', views.social_media_management, name='social_media_management'),
    path('services/social-media/ads/', views.social_media_ads, name='social_media_ads'),
    path('services/social-media/community/', views.community_management, name='community_management'),

    # Content Pages
    path('services/content/', views.content_overview, name='content_overview'),
    path('services/content/contentflow/', views.contentflow, name='contentflow'),
    path('services/content/creation/', views.content_creation, name='content_creation'),
    path('services/content/blog-writing/', views.blog_writing, name='blog_writing'),
    path('services/content/video-production/', views.video_production, name='video_production'),
    path('services/content/copywriting/', views.copywriting, name='copywriting'),

    # GBP Pages
    path('services/gbp/', views.gbp_overview, name='gbp_overview'),
    path('services/gbp/setup/', views.gbp_setup, name='gbp_setup'),
    path('services/gbp/management/', views.gbp_management, name='gbp_management'),
    path('services/gbp/optimization/', views.gbp_optimization, name='gbp_optimization'),

    # Ads Pages
    path('services/ads/', views.ads_overview, name='ads_overview'),
    path('services/ads/google-ads/', views.google_ads, name='google_ads'),
    path('services/ads/facebook-ads/', views.facebook_ads, name='facebook_ads'),
    path('services/ads/linkedin-ads/', views.linkedin_ads, name='linkedin_ads'),
    path('services/ads/management/', views.ads_management, name='ads_management'),

    # Packages Pages
    path('services/packages/', views.packages_overview, name='packages_overview'),
    path('services/packages/starter/', views.starter_package, name='starter_package'),
    path('services/packages/professional/', views.professional_package, name='professional_package'),
    path('services/packages/enterprise/', views.enterprise_package, name='enterprise_package'),
    path('services/packages/full-scale/', views.fullscale_package, name='fullscale_package'),

    # Other Services Pages
    path('services/other/backlinking/', views.backlinking, name='backlinking'),
    path('services/other/press-release/', views.press_release, name='press_release'),
    path('services/other/email-marketing/', views.email_marketing, name='email_marketing'),
    path('services/other/web-design/', views.web_design, name='web_design'),
    path('services/other/analytics/', views.analytics, name='analytics'),

    # Tools
    path('tools/', views.tools, name='tools'),
    path('tools/website-audit/', views.website_audit, name='website_audit'),
    path('tools/keyword-density/', views.keyword_density, name='keyword_density'),
    path('tools/seo-score/', views.seo_score, name='seo_score'),
    path('tools/serp-preview/', views.serp_preview, name='serp_preview'),
    path('tools/budget-planner/', views.budget_planner, name='budget_planner'),

    # API Endpoints
    path('api/check-audit-limit/', views.check_audit_limit, name='check_audit_limit'),
    path('api/start-audit/', views.start_website_audit, name='start_website_audit'),
    path('api/run-audit/', views.run_audit, name='run_audit'),
    path('api/get-audit-result/', views.get_audit_result, name='get_audit_result'),
    path('api/send-verification/', views.send_verification_email, name='send_verification_email'),
    path('api/verify-code/', views.verify_code, name='verify_code'),

    # Client Dashboard - Auth
    path('auth/login/', auth_views.login, name='auth_login'),
    path('auth/callback/', auth_views.callback, name='auth_callback'),
    path('auth/logout/', auth_views.logout_view, name='auth_logout'),

    # Client Dashboard - Main
    path('dashboard/', auth_views.dashboard, name='dashboard'),
    path('dashboard/scheduler/', auth_views.scheduler, name='scheduler'),
    path('dashboard/connect/<str:service>/', auth_views.connect_service, name='connect_service'),
    path('dashboard/connect/<str:service>/callback/', auth_views.connect_service_callback, name='connect_service_callback'),

    # Dashboard API
    path('api/dashboard/analytics/', auth_views.get_analytics_data, name='dashboard_analytics'),
    path('api/dashboard/search-console/', auth_views.get_search_console_data, name='dashboard_search_console'),
    path('api/dashboard/gbp/', auth_views.get_gbp_data, name='dashboard_gbp'),
    path('api/dashboard/disconnect/<str:service>/', auth_views.disconnect_service, name='dashboard_disconnect'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
