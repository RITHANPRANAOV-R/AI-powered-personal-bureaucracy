import requests

# ---------------------------
# OpenFDA
# ---------------------------
def search_openfda(drug_name: str) -> list:
    url = "https://api.fda.gov/drug/event.json"
    params = {
        "search": f"patient.drug.medicinalproduct:{drug_name}",
        "limit": 2
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        results = []
        for item in data.get("results", []):
            reaction = item.get("patient", {}).get("reaction", [{}])[0].get("reactionmeddrapt", "Unknown reaction")
            results.append({
                "title": f"FDA Adverse Event: {reaction}",
                "summary": f"Reported adverse event for {drug_name}: {reaction}",
                "url": "https://open.fda.gov"
            })
        return results
    except:
        return []

# ---------------------------
# RxNav
# ---------------------------
def search_rxnav(drug_name: str) -> list:
    try:
        url = f"https://rxnav.nlm.nih.gov/REST/drugs.json?name={drug_name}"
        r = requests.get(url, timeout=10)
        data = r.json()

        results = []
        drug_group = data.get("drugGroup", {})
        for group in drug_group.get("conceptGroup", []):
            for prop in group.get("conceptProperties", [])[:1]:
                results.append({
                    "title": f"RxNorm: {prop.get('name')}",
                    "summary": f"RxNorm concept ID: {prop.get('rxcui')}",
                    "url": "https://rxnav.nlm.nih.gov"
                })
        return results
    except:
        return []

# ---------------------------
# PubMed (NCBI)
# ---------------------------
def search_pubmed(query: str) -> list:
    try:
        # Step 1: search
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": 2
        }
        r = requests.get(search_url, params=params, timeout=10)
        ids = r.json()["esearchresult"]["idlist"]

        results = []

        # Step 2: fetch summaries
        if ids:
            fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            params = {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json"
            }
            r = requests.get(fetch_url, params=params, timeout=10)
            data = r.json()["result"]

            for pid in ids:
                article = data.get(pid, {})
                results.append({
                    "title": article.get("title", "PubMed Article"),
                    "summary": f"Journal: {article.get('fulljournalname', '')}",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"
                })

        return results
    except:
        return []

# ---------------------------
# WHO ICD-11
# ---------------------------
def search_who_icd(condition: str) -> list:
    try:
        # Public demo endpoint (no key needed)
        url = "https://id.who.int/icd/entity/search"
        params = {
            "q": condition,
            "linearization": "mms"
        }

        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        results = []
        for item in data.get("destinationEntities", [])[:2]:
            results.append({
                "title": f"ICD-11: {item.get('title', {}).get('@value', '')}",
                "summary": f"ICD Code: {item.get('theCode', '')}",
                "url": item.get("id", "https://icd.who.int")
            })

        return results
    except:
        return []

# ---------------------------
# NIH ClinicalTables
# ---------------------------
def search_clinical_tables(term: str) -> list:
    try:
        url = "https://clinicaltables.nlm.nih.gov/api/conditions/v3/search"
        params = {
            "terms": term,
            "maxList": 2,
            "df": "primary_name"
        }

        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        results = []
        if len(data) >= 4:
            names = data[3][0]
            for name in names:
                results.append({
                    "title": f"Condition: {name}",
                    "summary": f"ClinicalTables condition match: {name}",
                    "url": "https://clinicaltables.nlm.nih.gov"
                })

        return results
    except:
        return []
