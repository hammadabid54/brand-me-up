# Omni Path Marketing - Agent Configuration

## Brand Information
- **Brand Name:** Omni Path Marketing
- **Domain:** omnipathmarketing.com
- **Founder:** Hammad Abid
- **Headline:** Local & Global SEO Expert | Dental SEO & Digital Marketing Strategist | 10,000+ Dental Leads Generated
- **About:** 6+ years experience, 500+ businesses helped, SEMrush certified, specializing in Dental SEO

## Services Offered
- SEO (Local, E-commerce, SaaS, Technical, Enterprise)
- Social Media Marketing
- Content Creation & ContentFlow
- Google Business Profile (GBP) Management
- PPC/Ads (Google, Facebook, LinkedIn)
- Packages (Starter, Professional, Enterprise, Full-Scale)

## Website Structure
- Django 6.x with Bootstrap 5
- CMS with database models for pages, services, pricing, testimonials, FAQs
- Admin at /admin/
- Static files in /static/images/
- Media uploads in /media/

## Custom Agents

### 1. Content Writer Agent
**Purpose:** Write SEO-optimized content for web pages

**Capabilities:**
- Research and write page content (1000+ words for SEO)
- Create meta titles, descriptions, keywords
- Write hero sections, section content, FAQs
- Structure content for conversions
- Follow SEO best practices
- Use semantic SEO principles from seo-content-writer.md

**Skill File:** `seo-content-writer.md` - Contains full SEO content writing guidelines

**Output Format:**
```json
{
  "page_name": "about",
  "meta_title": "...",
  "meta_description": "...",
  "meta_keywords": "...",
  "hero_title": "...",
  "hero_subtitle": "...",
  "sections": [
    {
      "section_type": "about",
      "title": "...",
      "content": "..."
    }
  ],
  "faqs": [
    {"question": "...", "answer": "..."}
  ]
}
```

### 2. Web Developer Agent
**Purpose:** Publish content to the website CMS

**Capabilities:**
- Add/update pages in Django admin
- Create services with pricing plans
- Add testimonials and FAQs
- Update SEO meta tags
- Configure site settings

**Workflow:**
1. Receive content from Content Writer
2. Use Django admin or direct database access
3. Verify content appears correctly
4. Report status to user
