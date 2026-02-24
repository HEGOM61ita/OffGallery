"""
Geo Enricher - Arricchimento geografico offline da coordinate GPS.
Usa reverse_geocoder (offline, dati GeoNames bundled) per ottenere
città/regione/paese e costruire gerarchia XMP compatibile Lightroom.

Struttura gerarchia: Geo|{Continente}|{Paese}|{Regione}|{Città}
Esempio: Geo|Europe|Italy|Toscana|Firenze
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Mapping ISO 3166-1 alpha-2 → Continente ────────────────────────────────

CC_TO_CONTINENT: dict[str, str] = {
    # Africa
    'DZ': 'Africa', 'AO': 'Africa', 'BJ': 'Africa', 'BW': 'Africa', 'BF': 'Africa',
    'BI': 'Africa', 'CM': 'Africa', 'CV': 'Africa', 'CF': 'Africa', 'TD': 'Africa',
    'KM': 'Africa', 'CG': 'Africa', 'CD': 'Africa', 'CI': 'Africa', 'DJ': 'Africa',
    'EG': 'Africa', 'GQ': 'Africa', 'ER': 'Africa', 'ET': 'Africa', 'GA': 'Africa',
    'GM': 'Africa', 'GH': 'Africa', 'GN': 'Africa', 'GW': 'Africa', 'KE': 'Africa',
    'LS': 'Africa', 'LR': 'Africa', 'LY': 'Africa', 'MG': 'Africa', 'MW': 'Africa',
    'ML': 'Africa', 'MR': 'Africa', 'MU': 'Africa', 'MA': 'Africa', 'MZ': 'Africa',
    'NA': 'Africa', 'NE': 'Africa', 'NG': 'Africa', 'RW': 'Africa', 'ST': 'Africa',
    'SN': 'Africa', 'SC': 'Africa', 'SL': 'Africa', 'SO': 'Africa', 'ZA': 'Africa',
    'SS': 'Africa', 'SD': 'Africa', 'SZ': 'Africa', 'TZ': 'Africa', 'TG': 'Africa',
    'TN': 'Africa', 'UG': 'Africa', 'ZM': 'Africa', 'ZW': 'Africa', 'RE': 'Africa',
    'YT': 'Africa', 'EH': 'Africa', 'SH': 'Africa', 'TF': 'Africa',
    # Asia
    'AF': 'Asia', 'AM': 'Asia', 'AZ': 'Asia', 'BH': 'Asia', 'BD': 'Asia',
    'BT': 'Asia', 'BN': 'Asia', 'KH': 'Asia', 'CN': 'Asia', 'CY': 'Asia',
    'GE': 'Asia', 'HK': 'Asia', 'IN': 'Asia', 'ID': 'Asia', 'IR': 'Asia',
    'IQ': 'Asia', 'IL': 'Asia', 'JP': 'Asia', 'JO': 'Asia', 'KZ': 'Asia',
    'KW': 'Asia', 'KG': 'Asia', 'LA': 'Asia', 'LB': 'Asia', 'MO': 'Asia',
    'MY': 'Asia', 'MV': 'Asia', 'MN': 'Asia', 'MM': 'Asia', 'NP': 'Asia',
    'KP': 'Asia', 'KR': 'Asia', 'OM': 'Asia', 'PK': 'Asia', 'PS': 'Asia',
    'PH': 'Asia', 'QA': 'Asia', 'SA': 'Asia', 'SG': 'Asia', 'LK': 'Asia',
    'SY': 'Asia', 'TW': 'Asia', 'TJ': 'Asia', 'TH': 'Asia', 'TL': 'Asia',
    'TM': 'Asia', 'AE': 'Asia', 'UZ': 'Asia', 'VN': 'Asia', 'YE': 'Asia',
    'IO': 'Asia', 'CC': 'Asia', 'CX': 'Asia',
    # Europe
    'AL': 'Europe', 'AD': 'Europe', 'AT': 'Europe', 'BY': 'Europe', 'BE': 'Europe',
    'BA': 'Europe', 'BG': 'Europe', 'HR': 'Europe', 'CZ': 'Europe', 'DK': 'Europe',
    'EE': 'Europe', 'FI': 'Europe', 'FR': 'Europe', 'DE': 'Europe', 'GI': 'Europe',
    'GR': 'Europe', 'HU': 'Europe', 'IS': 'Europe', 'IE': 'Europe', 'IT': 'Europe',
    'LV': 'Europe', 'LI': 'Europe', 'LT': 'Europe', 'LU': 'Europe', 'MK': 'Europe',
    'MT': 'Europe', 'MD': 'Europe', 'MC': 'Europe', 'ME': 'Europe', 'NL': 'Europe',
    'NO': 'Europe', 'PL': 'Europe', 'PT': 'Europe', 'RO': 'Europe', 'SM': 'Europe',
    'RS': 'Europe', 'SK': 'Europe', 'SI': 'Europe', 'ES': 'Europe', 'SE': 'Europe',
    'CH': 'Europe', 'UA': 'Europe', 'GB': 'Europe', 'VA': 'Europe', 'RU': 'Europe',
    'XK': 'Europe', 'AX': 'Europe', 'FO': 'Europe', 'GG': 'Europe', 'IM': 'Europe',
    'JE': 'Europe', 'SJ': 'Europe',
    # North America
    'AG': 'North America', 'BS': 'North America', 'BB': 'North America',
    'BZ': 'North America', 'CA': 'North America', 'CR': 'North America',
    'CU': 'North America', 'DM': 'North America', 'DO': 'North America',
    'SV': 'North America', 'GD': 'North America', 'GT': 'North America',
    'HT': 'North America', 'HN': 'North America', 'JM': 'North America',
    'MX': 'North America', 'NI': 'North America', 'PA': 'North America',
    'KN': 'North America', 'LC': 'North America', 'VC': 'North America',
    'TT': 'North America', 'US': 'North America', 'AI': 'North America',
    'AW': 'North America', 'BQ': 'North America', 'VG': 'North America',
    'KY': 'North America', 'CW': 'North America', 'GP': 'North America',
    'MQ': 'North America', 'MS': 'North America', 'PR': 'North America',
    'SX': 'North America', 'TC': 'North America', 'VI': 'North America',
    'PM': 'North America', 'BL': 'North America', 'MF': 'North America',
    'GL': 'North America', 'BM': 'North America',
    # South America
    'AR': 'South America', 'BO': 'South America', 'BR': 'South America',
    'CL': 'South America', 'CO': 'South America', 'EC': 'South America',
    'GY': 'South America', 'PY': 'South America', 'PE': 'South America',
    'SR': 'South America', 'UY': 'South America', 'VE': 'South America',
    'FK': 'South America', 'GF': 'South America',
    # Oceania
    'AU': 'Oceania', 'FJ': 'Oceania', 'KI': 'Oceania', 'MH': 'Oceania',
    'FM': 'Oceania', 'NR': 'Oceania', 'NZ': 'Oceania', 'PW': 'Oceania',
    'PG': 'Oceania', 'WS': 'Oceania', 'SB': 'Oceania', 'TO': 'Oceania',
    'TV': 'Oceania', 'VU': 'Oceania', 'CK': 'Oceania', 'NU': 'Oceania',
    'PN': 'Oceania', 'TK': 'Oceania', 'WF': 'Oceania', 'AS': 'Oceania',
    'GU': 'Oceania', 'PF': 'Oceania', 'NC': 'Oceania', 'MP': 'Oceania',
    'NF': 'Oceania', 'HM': 'Oceania',
    # Antarctica
    'AQ': 'Antarctica', 'GS': 'Antarctica', 'BV': 'Antarctica',
}

# ─── Mapping ISO 3166-1 alpha-2 → Nome paese in inglese ─────────────────────

CC_TO_COUNTRY: dict[str, str] = {
    'AF': 'Afghanistan', 'AL': 'Albania', 'DZ': 'Algeria', 'AD': 'Andorra',
    'AO': 'Angola', 'AG': 'Antigua and Barbuda', 'AR': 'Argentina', 'AM': 'Armenia',
    'AU': 'Australia', 'AT': 'Austria', 'AZ': 'Azerbaijan', 'BS': 'Bahamas',
    'BH': 'Bahrain', 'BD': 'Bangladesh', 'BB': 'Barbados', 'BY': 'Belarus',
    'BE': 'Belgium', 'BZ': 'Belize', 'BJ': 'Benin', 'BT': 'Bhutan',
    'BO': 'Bolivia', 'BA': 'Bosnia and Herzegovina', 'BW': 'Botswana', 'BR': 'Brazil',
    'BN': 'Brunei', 'BG': 'Bulgaria', 'BF': 'Burkina Faso', 'BI': 'Burundi',
    'CV': 'Cape Verde', 'KH': 'Cambodia', 'CM': 'Cameroon', 'CA': 'Canada',
    'CF': 'Central African Republic', 'TD': 'Chad', 'CL': 'Chile', 'CN': 'China',
    'CO': 'Colombia', 'KM': 'Comoros', 'CG': 'Congo', 'CD': 'DR Congo',
    'CR': 'Costa Rica', 'CI': "Cote d'Ivoire", 'HR': 'Croatia', 'CU': 'Cuba',
    'CY': 'Cyprus', 'CZ': 'Czech Republic', 'DK': 'Denmark', 'DJ': 'Djibouti',
    'DM': 'Dominica', 'DO': 'Dominican Republic', 'EC': 'Ecuador', 'EG': 'Egypt',
    'SV': 'El Salvador', 'GQ': 'Equatorial Guinea', 'ER': 'Eritrea', 'EE': 'Estonia',
    'SZ': 'Eswatini', 'ET': 'Ethiopia', 'FJ': 'Fiji', 'FI': 'Finland',
    'FR': 'France', 'GA': 'Gabon', 'GM': 'Gambia', 'GE': 'Georgia',
    'DE': 'Germany', 'GH': 'Ghana', 'GR': 'Greece', 'GD': 'Grenada',
    'GT': 'Guatemala', 'GN': 'Guinea', 'GW': 'Guinea-Bissau', 'GY': 'Guyana',
    'HT': 'Haiti', 'HN': 'Honduras', 'HK': 'Hong Kong', 'HU': 'Hungary',
    'IS': 'Iceland', 'IN': 'India', 'ID': 'Indonesia', 'IR': 'Iran',
    'IQ': 'Iraq', 'IE': 'Ireland', 'IL': 'Israel', 'IT': 'Italy',
    'JM': 'Jamaica', 'JP': 'Japan', 'JO': 'Jordan', 'KZ': 'Kazakhstan',
    'KE': 'Kenya', 'KI': 'Kiribati', 'KP': 'North Korea', 'KR': 'South Korea',
    'KW': 'Kuwait', 'KG': 'Kyrgyzstan', 'LA': 'Laos', 'LV': 'Latvia',
    'LB': 'Lebanon', 'LS': 'Lesotho', 'LR': 'Liberia', 'LY': 'Libya',
    'LI': 'Liechtenstein', 'LT': 'Lithuania', 'LU': 'Luxembourg', 'MO': 'Macao',
    'MG': 'Madagascar', 'MW': 'Malawi', 'MY': 'Malaysia', 'MV': 'Maldives',
    'ML': 'Mali', 'MT': 'Malta', 'MH': 'Marshall Islands', 'MR': 'Mauritania',
    'MU': 'Mauritius', 'MX': 'Mexico', 'FM': 'Micronesia', 'MD': 'Moldova',
    'MC': 'Monaco', 'MN': 'Mongolia', 'ME': 'Montenegro', 'MA': 'Morocco',
    'MZ': 'Mozambique', 'MM': 'Myanmar', 'NA': 'Namibia', 'NR': 'Nauru',
    'NP': 'Nepal', 'NL': 'Netherlands', 'NZ': 'New Zealand', 'NI': 'Nicaragua',
    'NE': 'Niger', 'NG': 'Nigeria', 'MK': 'North Macedonia', 'NO': 'Norway',
    'OM': 'Oman', 'PK': 'Pakistan', 'PW': 'Palau', 'PS': 'Palestine',
    'PA': 'Panama', 'PG': 'Papua New Guinea', 'PY': 'Paraguay', 'PE': 'Peru',
    'PH': 'Philippines', 'PL': 'Poland', 'PT': 'Portugal', 'QA': 'Qatar',
    'RO': 'Romania', 'RU': 'Russia', 'RW': 'Rwanda', 'KN': 'Saint Kitts and Nevis',
    'LC': 'Saint Lucia', 'VC': 'Saint Vincent and the Grenadines', 'WS': 'Samoa',
    'SM': 'San Marino', 'ST': 'Sao Tome and Principe', 'SA': 'Saudi Arabia',
    'SN': 'Senegal', 'RS': 'Serbia', 'SC': 'Seychelles', 'SL': 'Sierra Leone',
    'SG': 'Singapore', 'SK': 'Slovakia', 'SI': 'Slovenia', 'SB': 'Solomon Islands',
    'SO': 'Somalia', 'ZA': 'South Africa', 'SS': 'South Sudan', 'ES': 'Spain',
    'LK': 'Sri Lanka', 'SD': 'Sudan', 'SR': 'Suriname', 'SE': 'Sweden',
    'CH': 'Switzerland', 'SY': 'Syria', 'TW': 'Taiwan', 'TJ': 'Tajikistan',
    'TZ': 'Tanzania', 'TH': 'Thailand', 'TL': 'Timor-Leste', 'TG': 'Togo',
    'TO': 'Tonga', 'TT': 'Trinidad and Tobago', 'TN': 'Tunisia', 'TR': 'Turkey',
    'TM': 'Turkmenistan', 'TV': 'Tuvalu', 'UG': 'Uganda', 'UA': 'Ukraine',
    'AE': 'United Arab Emirates', 'GB': 'United Kingdom', 'US': 'United States',
    'UY': 'Uruguay', 'UZ': 'Uzbekistan', 'VU': 'Vanuatu', 'VA': 'Vatican City',
    'VE': 'Venezuela', 'VN': 'Vietnam', 'YE': 'Yemen', 'ZM': 'Zambia',
    'ZW': 'Zimbabwe', 'XK': 'Kosovo', 'GL': 'Greenland',
}


def get_geo_hierarchy(lat: float, lon: float) -> Optional[str]:
    """
    Ritorna la gerarchia geografica offline da coordinate GPS.

    Args:
        lat: Latitudine decimale
        lon: Longitudine decimale

    Returns:
        Stringa tipo 'Geo|Europe|Italy|Toscana|Firenze' o None se fallisce
    """
    try:
        import reverse_geocoder as rg  # import lazy: caricato solo durante il processing

        results = rg.search((lat, lon), mode=1, verbose=False)
        if not results:
            logger.warning(f"reverse_geocoder: nessun risultato per ({lat}, {lon})")
            return None

        r = results[0]
        city = (r.get('name') or '').strip()
        admin1 = (r.get('admin1') or '').strip()
        cc = (r.get('cc') or '').upper()

        country = CC_TO_COUNTRY.get(cc, cc)
        continent = CC_TO_CONTINENT.get(cc, 'World')

        # Costruisci gerarchia eliminando livelli vuoti o ridondanti
        parts = ['Geo', continent, country]
        if admin1 and admin1.lower() != country.lower():
            parts.append(admin1)
        if city and city.lower() != admin1.lower() and city.lower() != country.lower():
            parts.append(city)

        hierarchy = '|'.join(p for p in parts if p)
        logger.debug(f"Geo hierarchy per ({lat:.4f}, {lon:.4f}): {hierarchy}")
        return hierarchy

    except ImportError:
        logger.warning("reverse_geocoder non installato — geotag non disponibile. "
                       "Installa con: pip install reverse_geocoder")
        return None
    except Exception as e:
        logger.error(f"Errore get_geo_hierarchy ({lat}, {lon}): {e}")
        return None


def get_location_hint(geo_hierarchy: str) -> Optional[str]:
    """
    Ritorna una stringa di contesto leggibile per il LLM.
    Esempio: 'Geo|Europe|Italy|Toscana|Firenze' → 'Firenze, Toscana, Italy'

    Prende gli ultimi 3 livelli significativi (escluso 'Geo') in ordine inverso.
    """
    if not geo_hierarchy:
        return None
    try:
        parts = [p for p in geo_hierarchy.split('|') if p and p != 'Geo']
        if not parts:
            return None
        # Ultimi 3 livelli in ordine inverso: città, regione, paese
        meaningful = parts[-3:]
        return ', '.join(reversed(meaningful))
    except Exception as e:
        logger.error(f"Errore get_location_hint: {e}")
        return None


def get_geo_leaf(geo_hierarchy: str) -> Optional[str]:
    """
    Ritorna il nodo foglia della gerarchia (città o luogo più specifico).
    Esempio: 'Geo|Europe|Italy|Toscana|Firenze' → 'Firenze'
    """
    if not geo_hierarchy:
        return None
    try:
        parts = [p for p in geo_hierarchy.split('|') if p and p != 'Geo']
        return parts[-1] if parts else None
    except Exception:
        return None
