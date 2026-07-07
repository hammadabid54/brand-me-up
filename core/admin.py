from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SiteSettings, Page, Section, ServiceCategory, Service,
    PricingPlan, Testimonial, FAQ, PortfolioItem, BlogPost
)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['site_name', 'contact_email', 'updated_at']
    fieldsets = (
        ('Basic Info', {
            'fields': ('site_name', 'site_tagline', 'logo', 'favicon')
        }),
        ('Contact Info', {
            'fields': ('contact_email', 'contact_phone', 'address', 'business_hours')
        }),
        ('SEO Settings', {
            'fields': ('default_meta_description', 'google_analytics_id')
        }),
        ('Custom Scripts', {
            'fields': ('header_scripts', 'footer_scripts'),
            'classes': ('collapse',)
        }),
        ('Social Links', {
            'fields': ('facebook_url', 'twitter_url', 'linkedin_url', 'instagram_url')
        }),
    )

    def has_add_permission(self, request):
        # Only allow one instance
        return not SiteSettings.objects.exists()


class SectionInline(admin.TabularInline):
    model = Section
    extra = 1
    fields = ['section_type', 'title', 'subtitle', 'content', 'image', 'order', 'is_active']
    ordering = ['order']


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ['title', 'page_name', 'slug', 'is_active', 'order']
    list_filter = ['is_active', 'page_name']
    search_fields = ['title', 'page_name', 'meta_description']
    prepopulated_fields = {'slug': ['page_name']}
    fieldsets = (
        ('Basic Info', {
            'fields': ('page_name', 'slug', 'title', 'is_active', 'order')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description', 'schema_markup')
        }),
        ('Hero Section', {
            'fields': ('hero_title', 'hero_subtitle', 'hero_image')
        }),
        ('Content', {
            'fields': ('content',)
        }),
    )
    inlines = [SectionInline]


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ['name']}


class PricingPlanInline(admin.TabularInline):
    model = PricingPlan
    extra = 1
    fields = ['name', 'price', 'description', 'features', 'is_popular', 'order']
    ordering = ['order']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'slug', 'is_active', 'order']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'description', 'meta_keywords']
    prepopulated_fields = {'slug': ['name']}
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'category', 'short_description', 'description', 'icon', 'image', 'order', 'is_active')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 'schema_markup')
        }),
    )
    inlines = [PricingPlanInline]


@admin.register(PricingPlan)
class PricingPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'service', 'price', 'is_popular', 'order']
    list_filter = ['is_popular', 'service']
    search_fields = ['name', 'service__name']


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'rating', 'is_active', 'order']
    list_filter = ['is_active', 'rating']
    search_fields = ['name', 'company', 'quote']
    fields = ['name', 'company', 'role', 'quote', 'avatar', 'rating', 'is_active', 'order']


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question', 'category', 'is_active', 'order']
    list_filter = ['is_active', 'category']
    search_fields = ['question', 'answer']
    fields = ['question', 'answer', 'category', 'is_active', 'order']


@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'client_name', 'category', 'is_active', 'order']
    list_filter = ['is_active', 'category']
    search_fields = ['title', 'client_name', 'description']
    prepopulated_fields = {'slug': ['title']}
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'slug', 'client_name', 'category', 'description', 'image', 'order', 'is_active')
        }),
        ('Details', {
            'fields': ('challenge', 'solution', 'results')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description')
        }),
    )


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'is_published', 'is_active', 'order', 'created_at']
    list_filter = ['is_published', 'is_active', 'created_at']
    search_fields = ['title', 'content', 'meta_keywords']
    prepopulated_fields = {'slug': ['title']}
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'slug', 'author', 'excerpt', 'content', 'image', 'order', 'is_published', 'is_active')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'meta_keywords')
        }),
    )
