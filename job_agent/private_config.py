"""Optional local confirmations and document roles; never writes or approves facts."""
import json
from pathlib import Path

ROLES = {'resume', 'cover_letter', 'answer_bank', 'profile_card', 'profile'}
GENERIC_NAMES = {'Resume.pdf': 'resume', 'Cover_letter.pdf': 'cover_letter',
                 'Answer_Bank.docx': 'answer_bank', 'Profile_Card.png': 'profile_card',
                 'Profile.pdf': 'profile'}


def local_configuration(private_root):
    path = Path(private_root) / 'privacy-refactor' / 'candidate-confirmations.json'
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('private_confirmation_invalid') from error
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('private_confirmation_invalid')
    return value


def document_role(item, private_root):
    explicit = item.get('role')
    if explicit is not None:
        return explicit if explicit in ROLES else None
    name = item.get('canonical_name', '')
    aliases = local_configuration(private_root).get('document_roles', {})
    if not isinstance(aliases, dict):
        raise ValueError('private_document_roles_invalid')
    role = aliases.get(name, GENERIC_NAMES.get(name))
    return role if role in ROLES else None


def document_for_role(entries, role, private_root):
    matches = [item for item in entries if document_role(item, private_root) == role]
    # Ambiguous roles never silently select a different approved document.
    return matches[0] if len(matches) == 1 else None


def confirmation(private_root):
    config = local_configuration(private_root)
    if not isinstance(config.get('confirmation_reference'), str) or not config['confirmation_reference'].strip() or not isinstance(config.get('updates'), dict):
        raise ValueError('explicit_local_confirmation_required')
    return config
