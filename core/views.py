from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count
from django.conf import settings
from core.content_loader import get_page_content
from core.models import WebsiteAudit
import requests
import json
import re

# MiniMax API Configuration
MINIMAX_API_KEY = "sk-cp-WkYLz80L8NKu54ssHzLmhIFyxvfKUbg7_8YMaPXKLVopTA_ymmDJyEIiBsghQKRbWKRfhXlG_fuiePS2NlkC2B5RQ2hadpblJvJVL2AabZ61JYYh5zR_LQ4"
MINIMAX_BASE_URL = "https://api.minimax.io"

# SEO Audit System Prompt
SEO_AUDIT_PROMPT = """You are an expert SEO auditor. Your job is to perform a thorough, structured audit of a web page and deliver a professional audit report covering on-page SEO, content quality, technical SEO, internal/external linking, and competitor benchmarking.

For each audit category, assign a traffic light status:
- Good (green) - meets best practice
- Warning (yellow) - room for improvement
- Critical (red) - actively hurting SEO performance

Categories to audit:
1. On-Page SEO: Title tag, Meta description, H1 tag, Heading hierarchy, URL structure, Keyword usage, Image alt text
2. Content Quality: Search intent match, Content depth, Word count, Readability, E-E-A-T signals, Freshness
3. Technical SEO: Page speed, Mobile-friendliness, Canonical tag, Robots meta, Structured data, Open Graph
4. Internal & External Linking: Internal links, Anchor text quality, External links, Link depth

Also include:
- Competitor Analysis (top 3 competitors for the target keyword)
- Action Plan with prioritized fixes (Quick Wins, Critical Fixes, Content Gaps)

Provide scores for each category (0-100) and an overall score.
Format your response as a detailed JSON object with the following structure:
{
  "overall_score": number,
  "on_page_seo": {"score": number, "issues": [], "recommendations": []},
  "content_quality": {"score": number, "issues": [], "recommendations": []},
  "technical_seo": {"score": number, "issues": [], "recommendations": []},
  "linking": {"score": number, "issues": [], "recommendations": []},
  "competitor_analysis": [],
  "action_plan": {"quick_wins": [], "critical_fixes": [], "content_gaps": []}
}

Be thorough and specific with recommendations."""

# Related services data for service pages
RELATED_SERVICES = {
    'seo': [
        {'name': 'Local SEO', 'url': '/services/seo/local-seo/', 'icon': 'map-marker-alt', 'description': 'Dominate your local market'},
        {'name': 'E-commerce SEO', 'url': '/services/seo/ecommerce-seo/', 'icon': 'shopping-cart', 'description': 'Boost online store traffic'},
        {'name': 'Technical SEO', 'url': '/services/seo/technical-seo/', 'icon': 'code', 'description': 'Optimize website performance'},
    ],
    'local_seo': [
        {'name': 'Google Business Profile', 'url': '/services/gbp/', 'icon': 'google', 'description': 'Manage your business listing'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'Build local brand awareness'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Create local content'},
    ],
    'ecommerce_seo': [
        {'name': 'Technical SEO', 'url': '/services/seo/technical-seo/', 'icon': 'code', 'description': 'Site optimization'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Product content creation'},
        {'name': 'Google Ads', 'url': '/services/ads/google-ads/', 'icon': 'ad', 'description': 'Paid traffic for e-commerce'},
    ],
    'saas_seo': [
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'SaaS content strategy'},
        {'name': 'Technical SEO', 'url': '/services/seo/technical-seo/', 'icon': 'code', 'description': 'Developer documentation SEO'},
        {'name': 'LinkedIn Ads', 'url': '/services/ads/linkedin-ads/', 'icon': 'linkedin', 'description': 'B2B lead generation'},
    ],
    'technical_seo': [
        {'name': 'Web Design', 'url': '/services/web-design/', 'icon': 'laptop', 'description': 'SEO-friendly websites'},
        {'name': 'E-commerce SEO', 'url': '/services/seo/ecommerce-seo/', 'icon': 'shopping-cart', 'description': 'Online store optimization'},
        {'name': 'Analytics', 'url': '/services/analytics/', 'icon': 'chart-bar', 'description': 'Track performance'},
    ],
    'enterprise_seo': [
        {'name': 'Technical SEO', 'url': '/services/seo/technical-seo/', 'icon': 'code', 'description': 'Large-scale optimization'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Enterprise content strategy'},
        {'name': 'Analytics', 'url': '/services/analytics/', 'icon': 'chart-bar', 'description': 'Advanced tracking'},
    ],
    'social_media_overview': [
        {'name': 'Social Media Management', 'url': '/services/social-media/management/', 'icon': 'calendar', 'description': 'Full-service management'},
        {'name': 'Social Media Ads', 'url': '/services/social-media/ads/', 'icon': 'bullhorn', 'description': 'Paid social campaigns'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Create engaging content'},
    ],
    'social_media_management': [
        {'name': 'Content Creation', 'url': '/services/content/creation/', 'icon': 'plus-circle', 'description': 'Professional content'},
        {'name': 'Community Management', 'url': '/services/social-media/community/', 'icon': 'users', 'description': 'Engage your audience'},
        {'name': 'Google Ads', 'url': '/services/ads/google-ads/', 'icon': 'ad', 'description': 'Complement with paid ads'},
    ],
    'social_media_ads': [
        {'name': 'Facebook Ads', 'url': '/services/ads/facebook-ads/', 'icon': 'facebook', 'description': 'Targeted Facebook campaigns'},
        {'name': 'LinkedIn Ads', 'url': '/services/ads/linkedin-ads/', 'icon': 'linkedin', 'description': 'B2B advertising'},
        {'name': 'Analytics', 'url': '/services/analytics/', 'icon': 'chart-bar', 'description': 'Track ad performance'},
    ],
    'community_management': [
        {'name': 'Social Media Management', 'url': '/services/social-media/management/', 'icon': 'calendar', 'description': 'Full-service management'},
        {'name': 'Content Creation', 'url': '/services/content/creation/', 'icon': 'plus-circle', 'description': 'Create engaging posts'},
        {'name': 'Social Media Ads', 'url': '/services/social-media/ads/', 'icon': 'bullhorn', 'description': 'Boost engagement'},
    ],
    'content_overview': [
        {'name': 'ContentFlow', 'url': '/services/content/contentflow/', 'icon': 'stream', 'description': 'Automated content'},
        {'name': 'Blog Writing', 'url': '/services/content/blog-writing/', 'icon': 'write', 'description': 'SEO blog content'},
        {'name': 'Copywriting', 'url': '/services/content/copywriting/', 'icon': 'copy', 'description': 'Persuasive copy'},
    ],
    'contentflow': [
        {'name': 'Content Creation', 'url': '/services/content/creation/', 'icon': 'plus-circle', 'description': 'Custom content'},
        {'name': 'Blog Writing', 'url': '/services/content/blog-writing/', 'icon': 'write', 'description': 'Regular blog posts'},
        {'name': 'Video Production', 'url': '/services/content/video-production/', 'icon': 'video', 'description': 'Video content'},
    ],
    'content_creation': [
        {'name': 'Blog Writing', 'url': '/services/content/blog-writing/', 'icon': 'write', 'description': 'SEO articles'},
        {'name': 'Copywriting', 'url': '/services/content/copywriting/', 'icon': 'copy', 'description': 'Marketing copy'},
        {'name': 'Video Production', 'url': '/services/content/video-production/', 'icon': 'video', 'description': 'Video content'},
    ],
    'blog_writing': [
        {'name': 'Copywriting', 'url': '/services/content/copywriting/', 'icon': 'copy', 'description': 'Website copy'},
        {'name': 'ContentFlow', 'url': '/services/content/contentflow/', 'icon': 'stream', 'description': 'Automated blogging'},
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Search optimization'},
    ],
    'video_production': [
        {'name': 'Content Creation', 'url': '/services/content/creation/', 'icon': 'plus-circle', 'description': 'Full content service'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'Video distribution'},
        {'name': 'YouTube Ads', 'url': '/services/ads/', 'icon': 'youtube', 'description': 'Video advertising'},
    ],
    'copywriting': [
        {'name': 'Blog Writing', 'url': '/services/content/blog-writing/', 'icon': 'write', 'description': 'Article writing'},
        {'name': 'Content Creation', 'url': '/services/content/creation/', 'icon': 'plus-circle', 'description': 'Full content suite'},
        {'name': 'Email Marketing', 'url': '/services/email-marketing/', 'icon': 'envelope', 'description': 'Email campaigns'},
    ],
    'gbp_overview': [
        {'name': 'Local SEO', 'url': '/services/seo/local-seo/', 'icon': 'search', 'description': 'Local search ranking'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'Local brand awareness'},
        {'name': 'Review Management', 'url': '/services/gbp/management/', 'icon': 'star', 'description': 'Manage reviews'},
    ],
    'gbp_setup': [
        {'name': 'GBP Optimization', 'url': '/services/gbp/optimization/', 'icon': 'trophy', 'description': 'Optimize your listing'},
        {'name': 'Local SEO', 'url': '/services/seo/local-seo/', 'icon': 'search', 'description': 'Local ranking'},
        {'name': 'GBP Management', 'url': '/services/gbp/management/', 'icon': 'cog', 'description': 'Ongoing management'},
    ],
    'gbp_management': [
        {'name': 'Review Management', 'url': '/services/gbp/optimization/', 'icon': 'star', 'description': 'Review optimization'},
        {'name': 'Local SEO', 'url': '/services/seo/local-seo/', 'icon': 'search', 'description': 'Local rankings'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'Engage customers'},
    ],
    'gbp_optimization': [
        {'name': 'GBP Setup', 'url': '/services/gbp/setup/', 'icon': 'plus', 'description': 'Complete setup'},
        {'name': 'Local SEO', 'url': '/services/seo/local-seo/', 'icon': 'search', 'description': 'Local presence'},
        {'name': 'Review Management', 'url': '/services/gbp/management/', 'icon': 'star', 'description': 'Review strategy'},
    ],
    'ads_overview': [
        {'name': 'Google Ads', 'url': '/services/ads/google-ads/', 'icon': 'google', 'description': 'Search advertising'},
        {'name': 'Facebook Ads', 'url': '/services/ads/facebook-ads/', 'icon': 'facebook', 'description': 'Social advertising'},
        {'name': 'LinkedIn Ads', 'url': '/services/ads/linkedin-ads/', 'icon': 'linkedin', 'description': 'B2B advertising'},
    ],
    'google_ads': [
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Organic growth'},
        {'name': 'Facebook Ads', 'url': '/services/ads/facebook-ads/', 'icon': 'facebook', 'description': 'Social ads'},
        {'name': 'Analytics', 'url': '/services/analytics/', 'icon': 'chart-bar', 'description': 'Track performance'},
    ],
    'facebook_ads': [
        {'name': 'Instagram Ads', 'url': '/services/ads/', 'icon': 'instagram', 'description': 'Visual advertising'},
        {'name': 'Google Ads', 'url': '/services/ads/google-ads/', 'icon': 'google', 'description': 'Search ads'},
        {'name': 'Social Media Management', 'url': '/services/social-media/management/', 'icon': 'calendar', 'description': 'Full management'},
    ],
    'linkedin_ads': [
        {'name': 'B2B Marketing', 'url': '/services/', 'icon': 'briefcase', 'description': 'B2B solutions'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'LinkedIn content'},
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Lead generation'},
    ],
    'ads_management': [
        {'name': 'Google Ads', 'url': '/services/ads/google-ads/', 'icon': 'google', 'description': 'Search ads'},
        {'name': 'Facebook Ads', 'url': '/services/ads/facebook-ads/', 'icon': 'facebook', 'description': 'Social ads'},
        {'name': 'Analytics', 'url': '/services/analytics/', 'icon': 'chart-bar', 'description': 'Performance tracking'},
    ],
    'backlinking': [
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Full SEO service'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Linkable content'},
        {'name': 'Press Release', 'url': '/services/press-release/', 'icon': 'newspaper', 'description': 'PR distribution'},
    ],
    'press_release': [
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'PR writing'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'PR distribution'},
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Media SEO'},
    ],
    'email_marketing': [
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Email content'},
        {'name': 'Copywriting', 'url': '/services/content/copywriting/', 'icon': 'copy', 'description': 'Email copy'},
        {'name': 'Analytics', 'url': '/services/analytics/', 'icon': 'chart-bar', 'description': 'Track open rates'},
    ],
    'web_design': [
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'SEO optimization'},
        {'name': 'E-commerce SEO', 'url': '/services/seo/ecommerce-seo/', 'icon': 'shopping-cart', 'description': 'Online store'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Website content'},
    ],
    'analytics': [
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Search analytics'},
        {'name': 'Google Ads', 'url': '/services/ads/google-ads/', 'icon': 'google', 'description': 'Ad analytics'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'Social analytics'},
    ],
    'other_services': [
        {'name': 'SEO', 'url': '/services/seo/', 'icon': 'search', 'description': 'Search optimization'},
        {'name': 'Social Media', 'url': '/services/social-media/', 'icon': 'share-alt', 'description': 'Social marketing'},
        {'name': 'Content Marketing', 'url': '/services/content/', 'icon': 'pencil-alt', 'description': 'Content strategy'},
    ],
}

def get_related_services(page_name):
    """Get related services for a given page name"""
    return RELATED_SERVICES.get(page_name, [])

# Create your views here.

def home(request):
    context = get_page_content('homepage.json')
    context.update({
        'meta_title': context.get('meta_title', 'Omni Path Marketing - Premier Digital Marketing Services & SEO Solutions'),
        'meta_description': context.get('meta_description', 'We provide AI-powered marketing solutions with human expertise. Services include SEO, social media marketing, content creation, and PPC advertising. Get results-driven digital marketing at competitive prices.'),
    })
    return render(request, 'home.html', context)

def services(request):
    context = get_page_content('services.json')
    context.update({
        'meta_title': context.get('meta_title', 'Digital Marketing Services - SEO, Social Media, Content & PPC | Omni Path Marketing'),
        'meta_description': context.get('meta_description', 'Explore our comprehensive digital marketing services. AI-powered SEO, social media marketing, content creation, Google Ads, and custom packages. Starting from $50/month.'),
    })
    return render(request, 'services/services.html', context)

def about(request):
    context = get_page_content('about.json')
    context.update({
        'meta_title': context.get('meta_title', 'About Us - Omni Path Marketing | Our Team & Mission'),
        'meta_description': context.get('meta_description', 'Learn about Omni Path Marketing - our team of experts, mission to make professional marketing accessible through AI technology, and commitment to results-driven strategies.'),
    })
    return render(request, 'about.html', context)

def portfolio(request):
    context = get_page_content('portfolio.json')
    context.update({
        'meta_title': context.get('meta_title', 'Portfolio - Our Work | Omni Path Marketing'),
        'meta_description': context.get('meta_description', 'View our portfolio of successful digital marketing campaigns. See how we\'ve helped businesses grow with SEO, social media, content, and PPC.'),
    })
    return render(request, 'portfolio.html', context)

def blog(request):
    context = get_page_content('blog.json')
    context.update({
        'meta_title': context.get('meta_title', 'Blog | Digital Marketing Tips & Insights | Omni Path Marketing'),
        'meta_description': context.get('meta_description', 'Read the latest digital marketing tips, SEO trends, social media strategies, and content marketing insights from Omni Path Marketing experts.'),
    })
    return render(request, 'blog/blog.html', context)

def contact(request):
    context = get_page_content('contact.json')
    context.update({
        'meta_title': context.get('meta_title', 'Contact Us | Omni Path Marketing'),
        'meta_description': context.get('meta_description', 'Contact Omni Path Marketing for a free consultation. We\'re ready to help with SEO, social media, content, and PPC marketing.'),
    })
    return render(request, 'contact.html', context)

@csrf_exempt
def contact_submit(request):
    if request.method == 'POST':
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        company = request.POST.get('company', '')
        service = request.POST.get('service', '')
        budget = request.POST.get('budget', '')
        message = request.POST.get('message', '')

        subject = f'New Contact Form Submission from {name}'
        email_message = f'''New contact form submission:

Name: {name}
Email: {email}
Phone: {phone}
Company: {company}
Interested Service: {service}
Budget: {budget}

Message:
{message}
'''
        try:
            send_mail(
                subject=subject,
                message=email_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['contact@brandmeup.org'],
                fail_silently=False,
            )
            messages.success(request, 'Thank you for your message! We\'ll get back to you within 24 hours.')
        except Exception as e:
            messages.error(request, 'There was an error sending your message. Please try again later.')

        return redirect('contact')

    return redirect('contact')

# SEO Service Pages
def seo_overview(request):
    context = get_page_content('seo_overview.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('seo')
    return render(request, 'services/service_page.html', context)

def local_seo(request):
    context = get_page_content('local_seo.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('local_seo')
    return render(request, 'services/service_page.html', context)

def ecommerce_seo(request):
    context = get_page_content('ecommerce_seo.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('ecommerce_seo')
    return render(request, 'services/service_page.html', context)

def saas_seo(request):
    context = get_page_content('saas_seo.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('saas_seo')
    return render(request, 'services/service_page.html', context)

def technical_seo(request):
    context = get_page_content('technical_seo.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('technical_seo')
    return render(request, 'services/service_page.html', context)

def enterprise_seo(request):
    context = get_page_content('enterprise_seo.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('enterprise_seo')
    return render(request, 'services/service_page.html', context)

# Social Media Pages
def social_media_overview(request):
    context = get_page_content('social_media_overview.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('social_media_overview')
    return render(request, 'services/service_page.html', context)

def social_media_management(request):
    context = get_page_content('social_media_management.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('social_media_management')
    return render(request, 'services/service_page.html', context)

def social_media_ads(request):
    context = get_page_content('social_media_ads.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('social_media_ads')
    return render(request, 'services/service_page.html', context)

def community_management(request):
    context = get_page_content('community_management.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('community_management')
    return render(request, 'services/service_page.html', context)

# Content Pages
def content_overview(request):
    context = get_page_content('content_overview.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('content_overview')
    return render(request, 'services/service_page.html', context)

def contentflow(request):
    context = get_page_content('contentflow.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('contentflow')
    return render(request, 'services/service_page.html', context)

def content_creation(request):
    context = get_page_content('content_creation.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('content_creation')
    return render(request, 'services/service_page.html', context)

def blog_writing(request):
    context = get_page_content('blog_writing.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('blog_writing')
    return render(request, 'services/service_page.html', context)

def video_production(request):
    context = get_page_content('video_production.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('video_production')
    return render(request, 'services/service_page.html', context)

def copywriting(request):
    context = get_page_content('copywriting.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('copywriting')
    return render(request, 'services/service_page.html', context)

# GBP Pages
def gbp_overview(request):
    context = get_page_content('gbp_overview.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('gbp_overview')
    return render(request, 'services/service_page.html', context)

def gbp_setup(request):
    context = get_page_content('gbp_setup.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('gbp_setup')
    return render(request, 'services/service_page.html', context)

def gbp_management(request):
    context = get_page_content('gbp_management.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('gbp_management')
    return render(request, 'services/service_page.html', context)

def gbp_optimization(request):
    context = get_page_content('gbp_optimization.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('gbp_optimization')
    return render(request, 'services/service_page.html', context)

# Ads Pages
def ads_overview(request):
    context = get_page_content('ads_overview.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('ads_overview')
    return render(request, 'services/service_page.html', context)

def google_ads(request):
    context = get_page_content('google_ads.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('google_ads')
    return render(request, 'services/service_page.html', context)

def facebook_ads(request):
    context = get_page_content('facebook_ads.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('facebook_ads')
    return render(request, 'services/service_page.html', context)

def linkedin_ads(request):
    context = get_page_content('linkedin_ads.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('linkedin_ads')
    return render(request, 'services/service_page.html', context)

def ads_management(request):
    context = get_page_content('ads_management.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('ads_management')
    return render(request, 'services/service_page.html', context)

# Packages Pages
def packages_overview(request):
    context = get_page_content('packages_overview.json')
    context['template'] = 'service_page'
    return render(request, 'services/service_page.html', context)

def starter_package(request):
    context = get_page_content('starter_package.json')
    context['template'] = 'service_page'
    return render(request, 'services/service_page.html', context)

def professional_package(request):
    context = get_page_content('professional_package.json')
    context['template'] = 'service_page'
    return render(request, 'services/service_page.html', context)

def enterprise_package(request):
    context = get_page_content('enterprise_package.json')
    context['template'] = 'service_page'
    return render(request, 'services/service_page.html', context)

def fullscale_package(request):
    context = get_page_content('fullscale_package.json')
    context['template'] = 'service_page'
    return render(request, 'services/service_page.html', context)

# Other Services Pages
def backlinking(request):
    context = get_page_content('backlinking.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('backlinking')
    return render(request, 'services/service_page.html', context)

def press_release(request):
    context = get_page_content('press_release.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('press_release')
    return render(request, 'services/service_page.html', context)

def email_marketing(request):
    context = get_page_content('email_marketing.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('email_marketing')
    return render(request, 'services/service_page.html', context)

def web_design(request):
    context = get_page_content('web_design.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('web_design')
    return render(request, 'services/service_page.html', context)

def analytics(request):
    context = get_page_content('analytics.json')
    context['template'] = 'service_page'
    context['related_services'] = get_related_services('analytics')
    return render(request, 'services/service_page.html', context)

def tools(request):
    """Free marketing tools page"""
    context = {
        'meta_title': 'Free Marketing Tools - SEO & Budget Planner | Omni Path Marketing',
        'meta_description': 'Free online marketing tools including SEO checker, keyword research, budget planner, and more. Boost your marketing effectiveness.',
        'meta_keywords': 'free marketing tools, SEO tools, keyword research tool, marketing budget planner',
    }
    return render(request, 'tools.html', context)

def website_audit(request):
    """Free website audit tool page"""
    context = {
        'meta_title': 'Free Website Audit Tool | Omni Path Marketing',
        'meta_description': 'Get a free comprehensive SEO audit of your website. Analyze on-page SEO, content quality, technical SEO, and get actionable recommendations.',
        'meta_keywords': 'free website audit, SEO audit tool, website analysis, SEO checker',
    }
    return render(request, 'tools/website-audit.html', context)

def keyword_density(request):
    """Keyword density checker tool page"""
    context = {
        'meta_title': 'Keyword Density Checker | Free SEO Tool | Omni Path Marketing',
        'meta_description': 'Free keyword density checker tool. Analyze keyword density in your content to optimize for search engines.',
        'meta_keywords': 'keyword density checker, SEO tool, keyword analysis',
    }
    return render(request, 'tools/keyword-density.html', context)

def seo_score(request):
    """SEO score checker tool page"""
    context = {
        'meta_title': 'SEO Score Checker | Free SEO Tool | Omni Path Marketing',
        'meta_description': 'Free SEO score checker tool. Check your website SEO score and get improvement recommendations.',
        'meta_keywords': 'SEO score checker, SEO analysis, website SEO',
    }
    return render(request, 'tools/seo-score.html', context)

def serp_preview(request):
    """SERP preview tool page"""
    context = {
        'meta_title': 'SERP Preview Tool | Free SEO Tool | Omni Path Marketing',
        'meta_description': 'Free SERP preview tool. Preview how your page will appear in Google search results.',
        'meta_keywords': 'SERP preview, Google preview, search results preview',
    }
    return render(request, 'tools/serp-preview.html', context)

def budget_planner(request):
    """Budget planner tool page"""
    context = {
        'meta_title': 'Budget Planner | Free Marketing Tool | Omni Path Marketing',
        'meta_description': 'Free marketing budget planner tool. Plan your marketing budget across different channels and campaigns.',
        'meta_keywords': 'budget planner, marketing budget, budget allocation',
    }
    return render(request, 'tools/budget-planner.html', context)


# ==================== API ENDPOINTS ====================

import random
import string
from django.core.mail import send_mail
from django.utils import timezone

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))


@csrf_exempt
def send_verification_email(request):
    """Send verification code to email"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = data.get('email', '').lower().strip()
        website_url = data.get('website_url', '').strip()
        target_keyword = data.get('target_keyword', '').strip()

        if not email:
            return JsonResponse({'success': False, 'message': 'Email is required'})
        if not website_url:
            return JsonResponse({'success': False, 'message': 'Website URL is required'})

        # Validate email format
        import re
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            return JsonResponse({'success': False, 'message': 'Please enter a valid email address'})

        # Check if URL is valid
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url

        # Generate verification code
        verification_code = generate_verification_code()

        # Create new audit record (don't update existing)
        audit = WebsiteAudit.objects.create(
            email=email,
            website_url=website_url,
            target_keyword=target_keyword,
            verification_code=verification_code,
            email_verified=False,
            verification_sent_at=timezone.now(),
            status='verification_sent'
        )

        # Send verification email
        try:
            send_mail(
                subject='Verify Your Email - Free Website Audit | Omni Path Marketing',
                message=f'''Hi,

Thank you for your interest in our Free Website Audit!

Your verification code is: {verification_code}

Please enter this 6-digit code on the website to verify your email and start your free audit.

This code will expire in 10 minutes.

Best regards,
Omni Path Marketing Team
''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            return JsonResponse({
                'success': True,
                'message': 'Verification code sent to your email',
                'verification_code': verification_code,
                'audit_id': audit.id
            })
        except Exception as e:
            # For testing, return the code in response
            return JsonResponse({
                'success': True,
                'message': 'Verification code: ' + verification_code + ' (Email disabled - using fallback mode)',
                'verification_code': verification_code,
                'audit_id': audit.id
            })

    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def verify_code(request):
    """Verify the code entered by user"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = data.get('email', '').lower().strip()
        code = data.get('code', '').strip()
        website_url = data.get('website_url', '').strip()
        target_keyword = data.get('target_keyword', '').strip()

        if not email or not code:
            return JsonResponse({'success': False, 'message': 'Email and code are required'})

        # Find the audit record
        audit = WebsiteAudit.objects.filter(
            email=email,
            verification_code=code,
            status='verification_sent'
        ).first()

        if not audit:
            return JsonResponse({'success': False, 'message': 'Invalid or expired verification code'})

        # Check if code is expired (10 minutes)
        if audit.verification_sent_at:
            time_diff = timezone.now() - audit.verification_sent_at
            if time_diff.total_seconds() > 600:  # 10 minutes
                return JsonResponse({'success': False, 'message': 'Verification code has expired. Please request a new one.'})

        # Mark as verified and start audit
        audit.email_verified = True
        audit.status = 'processing'
        if website_url and not audit.website_url:
            audit.website_url = website_url
        if target_keyword and not audit.target_keyword:
            audit.target_keyword = target_keyword
        audit.save()

        return JsonResponse({
            'success': True,
            'message': 'Email verified! Starting audit...',
            'audit_id': audit.id
        })

    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def check_audit_limit(request):
    """Check if email has already used their free audit"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = data.get('email', '').lower().strip()

        if not email:
            return JsonResponse({'allowed': False, 'message': 'Email is required'})

        # Check if email has already done an audit
        existing_audit = WebsiteAudit.objects.filter(email=email, status='completed').first()

        if existing_audit:
            return JsonResponse({
                'allowed': False,
                'message': 'You have already used your free audit. Contact us for more audits.'
            })

        return JsonResponse({'allowed': True, 'message': 'Email verified'})

    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def start_website_audit(request):
    """Start a new website audit"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)

        email = data.get('email', '').lower().strip()
        website_url = data.get('website_url', '').strip()
        target_keyword = data.get('target_keyword', '').strip()

        # Validation
        if not email or not website_url:
            return JsonResponse({'success': False, 'message': 'Email and website URL are required'})

        # Check if URL is valid
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url

        # Check limit
        existing_audit = WebsiteAudit.objects.filter(email=email, status='completed').first()
        if existing_audit:
            return JsonResponse({
                'success': False,
                'message': 'You have already used your free audit.'
            })

        # Create audit record
        audit = WebsiteAudit.objects.create(
            email=email,
            website_url=website_url,
            target_keyword=target_keyword,
            status='processing'
        )

        # Return the audit ID for polling
        return JsonResponse({
            'success': True,
            'audit_id': audit.id,
            'message': 'Audit started'
        })

    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def run_audit(request):
    """Run the actual audit using MiniMax AI with server-side scraping"""
    if request.method == 'POST':
        import json
        from bs4 import BeautifulSoup

        data = json.loads(request.body)
        audit_id = data.get('audit_id')

        try:
            audit = WebsiteAudit.objects.get(id=audit_id)
        except WebsiteAudit.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Audit not found'})

        # Server-side website scraping
        website_url = audit.website_url
        scraped_data = {
            'title': '',
            'meta_description': '',
            'meta_keywords': '',
            'h1_tags': [],
            'h2_tags': [],
            'headings': [],
            'main_content': '',
            'images': [],
            'links': [],
            'internal_links': [],
            'external_links': [],
            'word_count': 0,
            'has_robots': False,
            'has_canonical': False,
            'has_schema': False,
            'has_opengraph': False,
            'page_load_estimate': 'Unknown',
            'raw_html_length': 0
        }

        try:
            # Add common headers to mimic a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }

            # Fetch the website
            scrape_response = requests.get(website_url, headers=headers, timeout=30, allow_redirects=True)
            scraped_data['raw_html_length'] = len(scrape_response.text)

            if scrape_response.status_code != 200:
                audit.status = 'failed'
                audit.save()
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to fetch website: HTTP {scrape_response.status_code}'
                })

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(scrape_response.text, 'lxml')

            # Extract title
            if soup.title:
                scraped_data['title'] = soup.title.string or ''

            # Extract meta tags
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                scraped_data['meta_description'] = meta_desc.get('content', '')

            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                scraped_data['meta_keywords'] = meta_keywords.get('content', '')

            # Extract headings
            for h1 in soup.find_all('h1'):
                if h1.get_text(strip=True):
                    scraped_data['h1_tags'].append(h1.get_text(strip=True))

            for h2 in soup.find_all('h2'):
                if h2.get_text(strip=True):
                    scraped_data['h2_tags'].append(h2.get_text(strip=True))

            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                if heading.get_text(strip=True):
                    scraped_data['headings'].append(f"{heading.name.upper()}: {heading.get_text(strip=True)}")

            # Extract main content (from body, removing scripts and styles)
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()

            main_content = soup.find('body')
            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
                # Clean up whitespace
                text = ' '.join(text.split())
                scraped_data['main_content'] = text
                scraped_data['word_count'] = len(text.split())

            # Extract images with alt text
            for img in soup.find_all('img'):
                img_info = {
                    'src': img.get('src', ''),
                    'alt': img.get('alt', ''),
                    'has_alt': bool(img.get('alt', '').strip())
                }
                if img_info['src']:
                    scraped_data['images'].append(img_info)

            # Extract links
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                if href:
                    if href.startswith('/') or href.startswith(website_url):
                        scraped_data['internal_links'].append({'text': text, 'href': href})
                    elif href.startswith('http'):
                        scraped_data['external_links'].append({'text': text, 'href': href})
                    scraped_data['links'].append({'text': text, 'href': href})

            # Check for technical SEO elements
            if soup.find('meta', attrs={'name': 'robots'}):
                scraped_data['has_robots'] = True

            canonical = soup.find('link', attrs={'rel': 'canonical'})
            if canonical:
                scraped_data['has_canonical'] = True

            if soup.find('script', type='application/ld+json'):
                scraped_data['has_schema'] = True

            if soup.find('meta', property='og:title'):
                scraped_data['has_opengraph'] = True

        except requests.exceptions.Timeout:
            audit.status = 'failed'
            audit.save()
            return JsonResponse({'success': False, 'message': 'Website request timed out'})
        except requests.exceptions.ConnectionError:
            audit.status = 'failed'
            audit.save()
            return JsonResponse({'success': False, 'message': 'Could not connect to website'})
        except Exception as e:
            audit.status = 'failed'
            audit.save()
            return JsonResponse({'success': False, 'message': f'Scraping error: {str(e)}'})

        # Build the prompt with scraped data
        user_message = f"""Please audit this website:

Website URL: {website_url}
Target Keyword: {audit.target_keyword or 'Auto-detect from content'}

=== SCRAPED WEBSITE DATA ===

Title: {scraped_data['title']}

Meta Description: {scraped_data['meta_description']}

Meta Keywords: {scraped_data['meta_keywords']}

H1 Tags: {', '.join(scraped_data['h1_tags']) if scraped_data['h1_tags'] else 'None found'}

H2 Tags: {', '.join(scraped_data['h2_tags'][:10]) if scraped_data['h2_tags'] else 'None found'}

All Headings: {' | '.join(scraped_data['headings'][:20])}

Word Count: {scraped_data['word_count']}

Images (with alt text): {sum(1 for img in scraped_data['images'] if img['has_alt'])} / {len(scraped_data['images'])} have alt text

Internal Links: {len(scraped_data['internal_links'])}
External Links: {len(scraped_data['external_links'])}

Technical SEO:
- Has Robots Meta: {scraped_data['has_robots']}
- Has Canonical URL: {scraped_data['has_canonical']}
- Has Schema Markup: {scraped_data['has_schema']}
- Has Open Graph Tags: {scraped_data['has_opengraph']}

Main Content Preview (first 3000 chars):
{scraped_data['main_content'][:3000]}

=== END OF SCRAPED DATA ===

Provide a comprehensive SEO audit report in JSON format."""

        # Call MiniMax API
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            payload = {
                'model': 'MiniMax-M2.5',
                'messages': [
                    {'role': 'system', 'content': SEO_AUDIT_PROMPT},
                    {'role': 'user', 'content': user_message}
                ],
                'temperature': 0.7,
                'max_tokens': 4000
            }

            response = requests.post(
                f'{MINIMAX_BASE_URL}/v1/text/chatcompletion_v2',
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                audit.status = 'failed'
                audit.save()
                return JsonResponse({
                    'success': False,
                    'message': f'API error: {response.status_code} - {response.text}'
                })

            result = response.json()

            # Debug: Log the response structure
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"MiniMax Response: {result}")

            # MiniMax API response structure
            # May have 'choices' like OpenAI, or different format
            if 'choices' in result and len(result['choices']) > 0:
                audit_text = result['choices'][0]['message']['content']
            elif 'data' in result and len(result.get('data', [])) > 0:
                # Alternative MiniMax format
                audit_text = result['data'][0].get('content', '')
            elif 'text' in result:
                audit_text = result['text']
            else:
                audit.status = 'failed'
                audit.save()
                return JsonResponse({
                    'success': False,
                    'message': f'Unexpected API response format: {str(result)[:200]}'
                })

            # Try to parse JSON from response
            try:
                # Find JSON in response
                json_match = re.search(r'\{[\s\S]*\}', audit_text)
                if json_match:
                    audit_data = json.loads(json_match.group())
                    audit.audit_data = audit_data
                    audit.overall_score = audit_data.get('overall_score', 0)
            except:
                audit.audit_data = {'raw_audit': audit_text}

            audit.audit_report = audit_text
            audit.status = 'completed'
            audit.completed_at = timezone.now()
            audit.save()

            return JsonResponse({
                'success': True,
                'message': 'Audit completed',
                'score': audit.overall_score,
                'report': audit.audit_data if audit.audit_data else audit_text[:5000]
            })

        except Exception as e:
            audit.status = 'failed'
            audit.save()
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })

    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def get_audit_result(request):
    """Get audit result by ID"""
    if request.method == 'GET':
        audit_id = request.GET.get('audit_id')

        try:
            audit = WebsiteAudit.objects.get(id=audit_id)
            return JsonResponse({
                'status': audit.status,
                'score': audit.overall_score,
                'report': audit.audit_report[:2000] if audit.audit_report else None
            })
        except WebsiteAudit.DoesNotExist:
            return JsonResponse({'error': 'Audit not found'}, status=404)

    return JsonResponse({'error': 'Invalid request'}, status=400)
