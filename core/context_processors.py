from .models import SiteSettings, Page, ServiceCategory, Service, Testimonial, FAQ


def site_settings(request):
    """Add site settings to all templates"""
    try:
        settings = SiteSettings.objects.first()
    except SiteSettings.DoesNotExist:
        settings = None

    return {
        'site_settings': settings,
    }


def navigation(request):
    """Add navigation pages to all templates"""
    pages = Page.objects.filter(is_active=True).order_by('order')
    categories = ServiceCategory.objects.filter(is_active=True).order_by('order')

    # Get services for navigation
    services = Service.objects.filter(is_active=True).order_by('order')[:6]

    return {
        'nav_pages': pages,
        'service_categories': categories,
        'nav_services': services,
    }


def testimonials(request):
    """Add active testimonials to all templates"""
    return {
        'testimonials': Testimonial.objects.filter(is_active=True).order_by('order')[:10]
    }


def faqs(request):
    """Add FAQs to all templates"""
    return {
        'faqs': FAQ.objects.filter(is_active=True).order_by('order')
    }
