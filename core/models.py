from django.db import models
from django.utils.text import slugify
from django.conf import settings


class SiteSettings(models.Model):
    """Global site settings"""
    site_name = models.CharField(max_length=200, default='Omni Path Marketing')
    site_tagline = models.CharField(max_length=300, blank=True)
    logo = models.ImageField(upload_to='uploads/', blank=True, null=True)
    favicon = models.ImageField(upload_to='uploads/', blank=True, null=True)

    # Contact Info
    contact_email = models.EmailField(default='info@brandmeup.com')
    contact_phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    business_hours = models.CharField(max_length=200, blank=True)

    # SEO Settings
    default_meta_description = models.TextField(blank=True)
    google_analytics_id = models.CharField(max_length=50, blank=True)

    # Custom Scripts
    header_scripts = models.TextField(blank=True, help_text="Custom code to add in <head>")
    footer_scripts = models.TextField(blank=True, help_text="Custom code to add before </body>")

    # Social Links
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        if not self.pk and SiteSettings.objects.exists():
            return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class Page(models.Model):
    """Dynamic pages"""
    PAGE_CHOICES = [
        ('home', 'Home'),
        ('about', 'About'),
        ('services', 'Services'),
        ('portfolio', 'Portfolio'),
        ('blog', 'Blog'),
        ('contact', 'Contact'),
    ]

    page_name = models.CharField(max_length=50, choices=PAGE_CHOICES, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=200)

    # SEO
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    meta_keywords = models.CharField(max_length=300, blank=True)
    og_title = models.CharField(max_length=200, blank=True)
    og_description = models.TextField(blank=True)
    schema_markup = models.TextField(blank=True, help_text="JSON-LD schema markup")

    # Hero Section
    hero_title = models.CharField(max_length=300, blank=True)
    hero_subtitle = models.TextField(blank=True)
    hero_image = models.ImageField(upload_to='uploads/pages/', blank=True, null=True)

    # Content
    content = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'page_name']
        verbose_name = 'Page'
        verbose_name_plural = 'Pages'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.page_name)
        super().save(*args, **kwargs)


class Section(models.Model):
    """Page sections"""
    SECTION_TYPES = [
        ('hero', 'Hero Section'),
        ('about', 'About Section'),
        ('features', 'Features Section'),
        ('pricing', 'Pricing Section'),
        ('testimonials', 'Testimonials Section'),
        ('cta', 'Call to Action'),
        ('faq', 'FAQ Section'),
        ('contact', 'Contact Section'),
        ('custom', 'Custom Section'),
    ]

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='sections')
    section_type = models.CharField(max_length=50, choices=SECTION_TYPES)
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=300, blank=True)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='uploads/sections/', blank=True, null=True)
    image_2 = models.ImageField(upload_to='uploads/sections/', blank=True, null=True)

    # Additional fields as JSON
    extra_data = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'

    def __str__(self):
        return f"{self.page.title} - {self.get_section_type_display()}"


class ServiceCategory(models.Model):
    """Service categories"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fa-star', help_text="FontAwesome icon class")
    image = models.ImageField(upload_to='uploads/services/', blank=True, null=True)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Service Category'
        verbose_name_plural = 'Service Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Service(models.Model):
    """Marketing services"""
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=150)
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, related_name='services')

    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)

    # Icon and Image
    icon = models.CharField(max_length=50, default='fa-star', help_text="FontAwesome icon class")
    image = models.ImageField(upload_to='uploads/services/', blank=True, null=True)

    # SEO
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    meta_keywords = models.CharField(max_length=300, blank=True)
    schema_markup = models.TextField(blank=True)

    # Order
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Service'
        verbose_name_plural = 'Services'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class PricingPlan(models.Model):
    """Pricing plans for services"""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='pricing_plans')
    name = models.CharField(max_length=100)
    price = models.CharField(max_length=50, help_text="e.g., $99/month")
    description = models.CharField(max_length=200, blank=True)

    # Features stored as JSON list
    features = models.JSONField(default=list, help_text="List of features")

    is_popular = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Pricing Plan'
        verbose_name_plural = 'Pricing Plans'

    def __str__(self):
        return f"{self.service.name} - {self.name}"


class Testimonial(models.Model):
    """Client testimonials"""
    name = models.CharField(max_length=100)
    company = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=100, blank=True)
    quote = models.TextField()
    avatar = models.ImageField(upload_to='uploads/testimonials/', blank=True, null=True)
    rating = models.IntegerField(default=5, choices=[(i, i) for i in range(1, 6)])

    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'Testimonial'
        verbose_name_plural = 'Testimonials'

    def __str__(self):
        return f"{self.name} - {self.company}"


class FAQ(models.Model):
    """Frequently asked questions"""
    question = models.CharField(max_length=300)
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True, help_text="e.g., SEO, Pricing, General")

    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'question']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'

    def __str__(self):
        return self.question


class PortfolioItem(models.Model):
    """Portfolio/Case Studies"""
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=150, unique=True)
    client_name = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=100, blank=True, help_text="e.g., SEO, Social Media")

    description = models.TextField()
    challenge = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    results = models.TextField(blank=True)

    image = models.ImageField(upload_to='uploads/portfolio/', blank=True, null=True)
    gallery_images = models.JSONField(default=list, blank=True)

    # SEO
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'Portfolio Item'
        verbose_name_plural = 'Portfolio Items'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class BlogPost(models.Model):
    """Blog posts"""
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=150, unique=True)
    author = models.CharField(max_length=100, default='Hammad Abid')

    excerpt = models.CharField(max_length=300, blank=True)
    content = models.TextField()

    image = models.ImageField(upload_to='uploads/blog/', blank=True, null=True)

    # SEO
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    meta_keywords = models.CharField(max_length=300, blank=True)

    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'Blog Post'
        verbose_name_plural = 'Blog Posts'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class WebsiteAudit(models.Model):
    """Track website audit requests"""
    email = models.EmailField()
    website_url = models.URLField(max_length=500)
    target_keyword = models.CharField(max_length=200, blank=True)

    # Email verification
    verification_code = models.CharField(max_length=6, blank=True)
    email_verified = models.BooleanField(default=False)
    verification_sent_at = models.DateTimeField(null=True, blank=True)

    # Audit results
    audit_data = models.JSONField(default=dict, blank=True)
    audit_report = models.TextField(blank=True)
    overall_score = models.IntegerField(null=True, blank=True)

    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verification_sent', 'Verification Sent'),
        ('email_verified', 'Email Verified'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Website Audit'
        verbose_name_plural = 'Website Audits'

    def __str__(self):
        return f"{self.website_url} - {self.email}"


# ==================== Client Dashboard Models ====================

class Client(models.Model):
    """Client accounts for dashboard access"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='client_profile'
    )
    google_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    email = models.EmailField()
    name = models.CharField(max_length=200)
    profile_picture = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    # Agency client management
    is_agency_client = models.BooleanField(
        default=False,
        help_text='True if this client is managed by an agency (via invite link)'
    )
    agency = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='agency_clients',
        help_text='The agency Client who manages this client'
    )

    # Invite magic link
    invite_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    invite_token_expiry = models.DateTimeField(null=True, blank=True)
    invite_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'

    def __str__(self):
        return self.email


class ClientConnection(models.Model):
    """Google API connections for client accounts"""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='connections')

    SERVICE_CHOICES = [
        ('analytics', 'Google Analytics'),
        ('search_console', 'Google Search Console'),
        ('gbp', 'Google Business Profile'),
        ('meta_facebook', 'Meta Facebook'),
        ('meta_instagram', 'Meta Instagram'),
        ('linkedin', 'LinkedIn'),
        ('pinterest', 'Pinterest'),
    ]
    service = models.CharField(max_length=30, choices=SERVICE_CHOICES)

    # Token storage
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_expiry = models.DateTimeField(null=True, blank=True)

    # Service-specific data
    property_id = models.CharField(max_length=200, blank=True, help_text="GA4 Property ID or Search Console site URL")
    is_connected = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Client Connection'
        verbose_name_plural = 'Client Connections'
        unique_together = ['client', 'service']

    def __str__(self):
        return f"{self.client.email} - {self.service}"
