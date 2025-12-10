import os
from pathlib import Path
import fitz
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

def update_metadata(pdf_path, template, subject_template=None, title_template=None):
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening {pdf_path}: {e}")
        return

    metadata = doc.metadata

    filename = pdf_path.stem  # filename without extension

    # Convert template to regex pattern
    pattern, group_map = template_to_regex(template)
    match = re.match(pattern, filename)
    if match:
        # Extract fields based on group mapping
        author = None
        type = None
        year = None
        ausgabe = None
        month = None
        day = None

        for group_num, field_name in group_map.items():
            value = match.group(group_num)
            if field_name == 'author':
                author = value
            elif field_name == 'type':
                type = value
            elif field_name == 'year':
                year = value
            elif field_name == 'ausgabe':
                ausgabe = value
            elif field_name == 'month':
                month = value
            elif field_name == 'day':
                day = value

        # Build date string from year, month, day
        date_str = None
        if year and month and day:
            date_str = f"{year}-{month}-{day}"

        # Build title from template or use default
        if title_template:
            title = apply_template(title_template, {
                'author': author or '',
                'type': type or '',
                'year': year or '',
                'ausgabe': ausgabe or '',
                'month': month or '',
                'day': day or ''
            })
        else:
            title = f"{ausgabe}/{year[-2:]}"

        # Convert date to PDF format
        pdf_date = None
        try:
            date_obj = datetime.date.fromisoformat(date_str)
            pdf_date = f"D:{date_obj.strftime('%Y%m%d')}000000+00'00'"
        except (ValueError, TypeError):
            pass

        # Update metadata
        new_metadata = metadata.copy()
        new_metadata['author'] = author
        new_metadata['title'] = title
        new_metadata['keywords'] = author

        # Build subject from template or use default
        if subject_template:
            subject = apply_template(subject_template, {
                'author': author or '',
                'type': type or '',
                'year': year or '',
                'ausgabe': ausgabe or '',
                'month': month or '',
                'day': day or ''
            })
            new_metadata['subject'] = subject
        else:
            new_metadata['subject'] = f"{author} {type} {title}"
        new_metadata['creator'] = ''
        new_metadata['producer'] = ''
        new_metadata['trapped'] = ''
        if pdf_date:
            new_metadata['creationDate'] = pdf_date
            new_metadata['modDate'] = pdf_date

        doc.set_metadata(new_metadata)

        all_keys = set(metadata.keys()) | set(new_metadata.keys())

        # Print header
        print("─" * 128)
        print(f"{'Status':<8} {'Property':<20} {'Current Value':<45} {'Updated Value':<45}")
        print("─" * 128)

        # Print rows
        for key in sorted(all_keys):
            old_val = str(metadata.get(key, '')).replace('\n', ' ')[:43]
            new_val = str(new_metadata.get(key, '')).replace('\n', ' ')[:43]
            is_updated = old_val != new_val
            status_icon = "🔴" if is_updated else "🟢"
            print(f"{status_icon:<8} {key:<20} {old_val:<45} {new_val:<45}")

        print("─" * 128)
    else:
        # If filename doesn't match expected format, keep original metadata
        print(f"No update needed for {pdf_path} (filename format not recognized)")
    if doc.can_save_incrementally():
        doc.save(pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    else:
        doc.save(pdf_path)
    doc.close()

def main():
    # Get arguments from environment variables
    directory_path = os.getenv('DIRECTORY')
    template = os.getenv('TEMPLATE')
    subject_template = os.getenv('SUBJECT')
    title_template = os.getenv('TITLE')

    if not directory_path or not template:
        print("Error: Missing required environment variables")
        print("Required:")
        print("  DIRECTORY - Path to directory containing PDF files")
        print("  TEMPLATE - Filename template pattern")
        print("\nOptional:")
        print("  TITLE - Title metadata template (supports {author}, {type}, {year}, {ausgabe}, {month}, {day})")
        print("  SUBJECT - Subject metadata template (supports {author}, {type}, {year}, {ausgabe}, {month}, {day})")
        print("\nExample template: {author} {type} {year} - Ausgabe {ausgabe} ({year}-{month}-{day})")
        print("Example title: {ausgabe}/{year}")
        print("Example subject: {author} - {type} {ausgabe}/{year}")
        return 1

    directory = Path(directory_path)

    if not directory.is_dir():
        print("Error: Provided path is not a directory")
        return 1

    pdf_files = list(directory.rglob('*.pdf'))
    if not pdf_files:
        print("No PDF files found in the directory.")
        return 0

    for pdf_file in pdf_files:
        print(f"Processing {pdf_file}")
        try:
            update_metadata(pdf_file, template, subject_template, title_template)
            print(f"Updated metadata for {pdf_file}")
            print()
        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")
            print()

    return 0

if __name__ == "__main__":
    main()