"""
Utility functions to load JSON content for the website.
"""
import json
import os
import re
from django.conf import settings


def load_content_json(filename):
    """
    Load content from a JSON file in the content directory.
    """
    content_dir = os.path.join(settings.BASE_DIR, 'content')
    file_path = os.path.join(content_dir, filename)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Content file not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return {}


def parse_content_blocks(text):
    """
    Parse content text into structured blocks for beautiful display.
    Each item that looks like a heading followed by description becomes a separate card.
    """
    if not text:
        return []

    blocks = []

    # Split by double newlines to get paragraphs
    paragraphs = re.split(r'\n\n+', text)

    # Check if has explicit bullets
    full_text = '\n\n'.join([p.strip() for p in paragraphs if p.strip()])

    has_explicit_bullets = '•' in full_text or '- ' in full_text

    if has_explicit_bullets:
        # Parse explicit bullet list
        items = []
        lines = full_text.split('\n')
        current_item = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('•') or line.startswith('- '):
                if current_item:
                    items.append(_parse_item(current_item))
                current_item = re.sub(r'^[•\-\s]+\s*', '', line)
            else:
                current_item += " " + line

        if current_item:
            items.append(_parse_item(current_item))

        if items:
            blocks.append({'type': 'bullet_list', 'items': items})
        else:
            blocks.append({'type': 'paragraph', 'text': full_text})
    else:
        # No explicit bullets - parse each line as potential card
        # Look for pattern: "Heading: Description" on each line
        lines = full_text.split('\n')
        all_items = []
        intro_text = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line is an HTML heading tag - preserve as paragraph
            is_html_heading = re.match(r'^<h[1-6]', line, re.IGNORECASE)

            # Check if line matches "Title: Description" pattern
            # Title should be short (not too many words) and end with colon
            is_card = (
                not is_html_heading and  # Skip if it's an HTML heading
                re.match(r'^[A-Z][A-Za-z\s]+:', line) and  # Starts with capitalized words and colon
                len(line.split(':')[0].split()) <= 5  # Title is short
            )

            if is_card:
                all_items.append(_parse_item(line))
            else:
                intro_text.append(line)

        # Add intro paragraphs
        if intro_text:
            combined = ' '.join(intro_text)
            if combined:
                blocks.append({'type': 'paragraph', 'text': combined})

        # Add cards
        if all_items:
            blocks.append({'type': 'bullet_list', 'items': all_items})

    return blocks


def _parse_item(text):
    """Parse a single item into title and description."""
    text = text.strip()

    # Check for colon separator
    if ':' in text:
        parts = text.split(':', 1)
        title = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ''
        return {'title': title, 'description': description}
    else:
        return {'title': text, 'description': ''}


def get_page_content(content_file):
    """
    Get all content from a JSON file and prepare it for the template.
    """
    content = load_content_json(content_file)

    # Process sections to create structured blocks
    sections = content.get('sections', [])
    formatted_sections = []

    for section in sections:
        formatted_section = section.copy()

        # Parse content into blocks
        if 'content' in formatted_section:
            formatted_section['content_blocks'] = parse_content_blocks(formatted_section['content'])

        formatted_sections.append(formatted_section)

    # Build context dictionary
    context = {
        # Meta tags
        'meta_title': content.get('meta_title', ''),
        'meta_description': content.get('meta_description', ''),
        'meta_keywords': content.get('meta_keywords', ''),
        'page_name': content.get('page_name', ''),
        'service_name': content.get('service_name', ''),
        'slug': content.get('slug', ''),
        'category': content.get('category', ''),
        'category_url': content.get('category_url', ''),
        'description': content.get('description', ''),

        # Hero section
        'hero_title': content.get('hero_title', ''),
        'hero_subtitle': content.get('hero_subtitle', ''),

        # Sections with parsed blocks
        'sections': formatted_sections,

        # Pricing
        'pricing_intro': content.get('pricing', {}).get('intro', ''),
        'pricing_description': content.get('pricing', {}).get('description', ''),
        'pricing_plans': content.get('pricing', {}).get('plans', []),

        # FAQs
        'faqs': content.get('faqs', []),

        # Sample posts
        'sample_posts': content.get('sample_posts', []),

        # CTA
        'cta_title': content.get('cta', {}).get('title', ''),
        'cta_subtitle': content.get('cta', {}).get('subtitle', ''),
        'cta_button_text': content.get('cta', {}).get('button_text', ''),
        'cta_button_url': content.get('cta', {}).get('button_url', ''),
    }

    return context
