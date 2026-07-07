from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count
from django.conf import settings
from core.content_loader import get_page_content
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
        'meta_title': context.get('meta_title', 'Brand Me Up - Premier Digital Marketing Services & SEO Solutions'),
        'meta_description': context.get('meta_description', 'We provide AI-powered marketing solutions with human expertise. Services include SEO, social media marketing, content creation, and PPC advertising. Get results-driven digital marketing at competitive prices.'),
    })
    return render(request, 'home.html', context)

def services(request):
    context = get_page_content('services.json')
    context.update({
        'meta_title': context.get('meta_title', 'Digital Marketing Services - SEO, Social Media, Content & PPC | Brand Me Up'),
        'meta_description': context.get('meta_description', 'Explore our comprehensive digital marketing services. AI-powered SEO, social media marketing, content creation, Google Ads, and custom packages. Starting from $50/month.'),
    })
    return render(request, 'services/services.html', context)

def about(request):
    context = get_page_content('about.json')
    context.update({
        'meta_title': context.get('meta_title', 'About Us - Brand Me Up | Our Team & Mission'),
        'meta_description': context.get('meta_description', 'Learn about Brand Me Up - our team of experts, mission to make professional marketing accessible through AI technology, and commitment to results-driven strategies.'),
    })
    return render(request, 'about.html', context)

def portfolio(request):
    context = get_page_content('portfolio.json')
    context.update({
        'meta_title': context.get('meta_title', 'Portfolio - Our Work | Brand Me Up'),
        'meta_description': context.get('meta_description', 'View our portfolio of successful digital marketing campaigns. See how we\'ve helped businesses grow with SEO, social media, content, and PPC.'),
    })
    return render(request, 'portfolio.html', context)

def blog(request):
    context = get_page_content('blog.json')
    context.update({
        'meta_title': context.get('meta_title', 'Blog | Digital Marketing Tips & Insights | Brand Me Up'),
        'meta_description': context.get('meta_description', 'Read the latest digital marketing tips, SEO trends, social media strategies, and content marketing insights from Brand Me Up experts.'),
    })
    return render(request, 'blog/blog.html', context)

def contact(request):
    context = get_page_content('contact.json')
    context.update({
        'meta_title': context.get('meta_title', 'Contact Us | Brand Me Up'),
        'meta_description': context.get('meta_description', 'Contact Brand Me Up for a free consultation. We\'re ready to help with SEO, social media, content, and PPC marketing.'),
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
