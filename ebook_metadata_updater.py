import os
from pathlib import Path
import pikepdf
import re
import datetime

def template_to_regex(template):
    """
    Convert a flexible template to a regex pattern.
    Returns both the regex pattern and a mapping of group numbers to field names.
    Placeholders: {author}, {type}, {year}, {ausgabe}, {month}, {day}
    """
    # Find all placeholders in the template in order
    placeholder_pattern = r'\{(author|type|year|ausgabe|month|day)\}'
    placeholders = re.findall(placeholder_pattern, template)

    # Create mapping of group number to field name (only for capturing groups)
    group_map = {}
    group_num = 1
    for placeholder in placeholders:
        if placeholder in ('author', 'type', 'year', 'ausgabe'):
            group_map[group_num] = placeholder
            group_num += 1
        elif placeholder == 'month':
            group_map[group_num] = 'month'
            group_num += 1
        elif placeholder == 'day':
            group_map[group_num] = 'day'
            group_num += 1

    # Escape special regex characters
    pattern = re.escape(template)
    pattern = pattern.replace(r'\{author\}', r'(.+?)')
    pattern = pattern.replace(r'\{type\}', r'(.+?)')
    pattern = pattern.replace(r'\{year\}', r'(\d{4})')
    pattern = pattern.replace(r'\{ausgabe\}', r'(\d+)')
    pattern = pattern.replace(r'\{month\}', r'(\d{2})')
    pattern = pattern.replace(r'\{day\}', r'(\d{2})')

    return f"^{pattern}$", group_map

def apply_template(template, fields):
    """
    Apply template with support for both plain placeholders and slicing syntax.
    Examples: {year}, {year[-2:]}, {ausgabe[1:]}
    """
    result = template
    # Match placeholders with optional slicing syntax: {field} or {field[slice]}
    pattern = r'\{([a-z]+)(\[[^\]]*\])?\}'

    def replace_placeholder(match):
        field_name = match.group(1)
        slice_syntax = match.group(2)

        value = fields.get(field_name, '')
        if value and slice_syntax:
            try:
                # Safely evaluate the slice
                value = eval(f"value{slice_syntax}")
            except (SyntaxError, TypeError, IndexError):
                pass
        return str(value)

    result = re.sub(pattern, replace_placeholder, result)
    return result

def extract_fields_from_filename(filename, pattern, group_map):
    """Extract metadata fields from filename using regex groups."""
    match = re.match(pattern, filename)
    if not match:
        return None

    fields = {'author': None, 'type': None, 'year': None, 'ausgabe': None, 'month': None, 'day': None}

    for group_num, field_name in group_map.items():
        fields[field_name] = match.group(group_num)

    return fields

def get_metadata(meta):
    """Extract metadata from PDF metadata object."""
    return {
        'dc:creator': str(meta.get('dc:creator', '')),
        'dc:date': str(meta.get('dc:date', '')),
        'dc:description': str(meta.get('dc:description', '')),
        'dc:subject': str(meta.get('dc:subject', '')),
        'dc:title': str(meta.get('dc:title', '')),
        'xmp:CreateDate': str(meta.get('xmp:CreateDate', '')),
        'xmp:CreatorTool': str(meta.get('xmp:CreatorTool', ''))
    }

def log_available_metadata(meta):
    """Log all available metadata fields in PDF."""
    print(f"Available metadata fields in PDF:")
    for key in sorted(meta.keys()):
        print(f"  {key}: {meta.get(key, '')}")
    print()

def build_title(title_template, fields, default_title):
    """Build title from template or use default."""
    if title_template:
        return apply_template(title_template, fields)
    return default_title

def build_subject(subject_template, fields, default_subject):
    """Build subject from template or use default."""
    if subject_template:
        return apply_template(subject_template, fields)
    return default_subject

def build_description(description_template, fields, default_description):
    """Build description from template or use default."""
    if description_template:
        return apply_template(description_template, fields)
    return default_description

def update_metadata_fields(metadata, author, title, subject, description, creator_tool):
    """Update metadata fields in the PDF."""
    metadata['dc:creator'] = [author] if author else []
    metadata['dc:description'] = description
    metadata['dc:subject'] = {subject} if subject else set()
    metadata['dc:title'] = title
    metadata['xmp:CreatorTool'] = creator_tool

def print_metadata_comparison(current_metadata, new_metadata):
    """Print formatted metadata comparison table."""
    all_keys = set(current_metadata.keys()) | set(new_metadata.keys())

    # Print header
    print("─" * 128)
    print(f"{'Status':<8} {'Property':<20} {'Current Value':<45} {'Updated Value':<45}")
    print("─" * 128)

    # Print rows
    for key in sorted(all_keys):
        old_val = str(current_metadata.get(key, '')).replace('\n', ' ')[:43]
        new_val = str(new_metadata.get(key, '')).replace('\n', ' ')[:43]
        is_updated = old_val != new_val
        status_icon = "🔴" if is_updated else "🟢"
        print(f"{status_icon:<8} {key:<20} {old_val:<45} {new_val:<45}")

    print("─" * 128)

def update_metadata(pdf_path, template, subject_template=None, title_template=None, description_template=None, log_available=False):
    try:
        pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)
    except Exception as e:
        print(f"Error opening {pdf_path}: {e}")
        return

    # Get current metadata for comparison
    meta = pdf.open_metadata()

    if log_available:
        log_available_metadata(meta)

    current_metadata = get_metadata(meta)

    filename = pdf_path.stem  # filename without extension

    # Convert template to regex pattern
    pattern, group_map = template_to_regex(template)
    fields = extract_fields_from_filename(filename, pattern, group_map)

    if not fields:
        print(f"No update needed for {pdf_path} (filename format not recognized)")
        return

    author = fields['author']
    type = fields['type']
    year = fields['year']
    ausgabe = fields['ausgabe']
    month = fields['month']
    day = fields['day']

    # Build title and subject
    field_values = {
        'author': author or '',
        'type': type or '',
        'year': year or '',
        'ausgabe': ausgabe or '',
        'month': month or '',
        'day': day or ''
    }

    default_title = f"{ausgabe}/{year[-2:]}" if ausgabe and year else ""
    title = build_title(title_template, field_values, default_title)

    default_subject = f"{author} {type} {title}"
    subject = build_subject(subject_template, field_values, default_subject)

    default_description = f"{author} {type} {title}"
    description = build_description(description_template, field_values, default_description)

    # Update metadata using pikepdf's XMP metadata API
    with pdf.open_metadata() as metadata:
        update_metadata_fields(metadata, author, title, subject, description, '')

    # Get updated metadata for comparison
    meta = pdf.open_metadata()
    new_metadata = get_metadata(meta)

    # Print metadata comparison
    print_metadata_comparison(current_metadata, new_metadata)

    # Save changes to PDF only if metadata was changed
    if current_metadata != new_metadata:
        pdf.save(pdf_path)
        print("💾 Metadata saved successfully")
    else:
        print("✅ No changes made to metadata")

    pdf.close()

def main():
    # Get arguments from environment variables
    directory_path = os.getenv('DIRECTORY')
    template = os.getenv('TEMPLATE')
    subject_template = os.getenv('SUBJECT')
    title_template = os.getenv('TITLE')
    description_template = os.getenv('DESCRIPTION')
    log_available = os.getenv('LOG_AVAILABLE', 'false').lower() == 'true'

    if not directory_path or not template:
        print("Error: Missing required environment variables")
        print("Required:")
        print("  DIRECTORY - Path to directory containing PDF files")
        print("  TEMPLATE - Filename template pattern")
        print("\nOptional:")
        print("  TITLE - Title metadata template (supports {author}, {type}, {year}, {ausgabe}, {month}, {day})")
        print("  SUBJECT - Subject metadata template (supports {author}, {type}, {year}, {ausgabe}, {month}, {day})")
        print("  DESCRIPTION - Description metadata template (supports {author}, {type}, {year}, {ausgabe}, {month}, {day})")
        print("\nExample template: {author} {type} {year} - Ausgabe {ausgabe} ({year}-{month}-{day})")
        print("Example title: {ausgabe}/{year}")
        print("Example subject: {author} - {type} {ausgabe}/{year}")
        print("Example description: {author} - {type} - Ausgabe {ausgabe}")
        return 1

    directory = Path(directory_path)

    if not directory.is_dir():
        print("Error: Provided path is not a directory")
        return 1

    pdf_files = sorted(directory.rglob('*.pdf'))
    if not pdf_files:
        print("No PDF files found in the directory.")
        return 0

    for pdf_file in pdf_files:
        print(f"Processing {pdf_file}")
        try:
            update_metadata(pdf_file, template, subject_template, title_template, description_template, log_available)
            print()
        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")
            print()

    print("All done.")

    return 0

if __name__ == "__main__":
    main()