"""Human-declaration boundary using control structure and the assertion's meaning."""
import re


def human_control(field):
    if field.get('legal_control') or field.get('type') in {'checkbox','password','submit','image'}:return True
    text=' '.join(str(field.get(k) or '') for k in ('label','group','instructions')).casefold()
    # A first-person performative is a decision/declaration, not a contact fact.
    if re.search(r'\bi\s+(?:(?:hereby|explicitly)\s+)?(?:confirm|certify|acknowledge|agree|consent|attest|declare|accept|authorize|authorise|understand)\b',text):return True
    if re.search(r'by (?:continuing|selecting|clicking|proceeding).{0,100}(?:agree|accept|authoriz|consent)|(?:allow|permit|permission).{0,100}(?:process|share|disclose).{0,100}(?:personal|data|details)',text):return True
    legal=re.search(r'privacy|terms (?:of|and)|consent|attestation|legal declaration|electronic signature|binding agreement',text)
    accuracy=re.search(r'(?:information|statements?|answers?|details).{0,100}(?:true|accurate|correct|complete|truthful)|(?:true|accurate|correct).{0,100}(?:information|statements?|answers?)',text)
    if legal or accuracy:return True
    if re.search(r'\b(?:certify|attest|declare under|accept terms|create account|sign up|submit application)\b',text):return True
    return False
