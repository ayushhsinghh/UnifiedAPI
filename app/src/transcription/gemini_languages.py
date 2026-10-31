"""Documented Gemini Live Translate BCP-47 targets (not Whisper's language list)."""
LANGUAGES = dict(line.split('|') for line in '''af|Afrikaans
ak|Akan
sq|Albanian
am|Amharic
ar|Arabic
hy|Armenian
az|Azerbaijani
eu|Basque
be|Belarusian
bn|Bengali
bg|Bulgarian
my|Burmese
ca|Catalan
zh-Hans|Chinese (Simplified)
zh-Hant|Chinese (Traditional)
hr|Croatian
cs|Czech
da|Danish
nl|Dutch
en|English
et|Estonian
fil|Filipino
fi|Finnish
fr|French
gl|Galician
ka|Georgian
de|German
el|Greek
gu|Gujarati
ha|Hausa
he|Hebrew
hi|Hindi
hu|Hungarian
is|Icelandic
id|Indonesian
it|Italian
ja|Japanese
jv|Javanese
kn|Kannada
kk|Kazakh
km|Khmer
rw|Kinyarwanda
ko|Korean
lo|Lao
lv|Latvian
lt|Lithuanian
mk|Macedonian
ms|Malay
ml|Malayalam
mr|Marathi
mn|Mongolian
ne|Nepali
no|Norwegian
nb|Norwegian (Bokmål)
fa|Persian
pl|Polish
pt-BR|Portuguese (Brazil)
pt-PT|Portuguese (Portugal)
pa|Punjabi
ro|Romanian
ru|Russian
sr|Serbian
sd|Sindhi
si|Sinhala
sk|Slovak
sl|Slovenian
es|Spanish
su|Sundanese
sw|Swahili
sv|Swedish
ta|Tamil
te|Telugu
th|Thai
tr|Turkish
uk|Ukrainian
ur|Urdu
uz|Uzbek
vi|Vietnamese
zu|Zulu'''.splitlines())


def whisper_language(code):
    """Whisper's tokenizer uses base codes and `tl` for Filipino."""
    if code in {'ak', 'rw'}:
        return None
    return {'zh-Hans': 'zh', 'zh-Hant': 'zh', 'fil': 'tl', 'nb': 'no'}.get(code, code.split('-')[0])
