import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_dataset_variables(dataset_id="ascat_daily_datasets"):
    # The /info/ endpoint reveals the internal variables of any ERDDAP dataset
    url = f"https://erddap.incois.gov.in/erddap/info/{dataset_id}/index.json"
    
    try:
        print(f"Fetching schema for {dataset_id}...\n")
        response = requests.get(url, timeout=15, verify=False)
        response.raise_for_status()
        
        rows = response.json()["table"]["rows"]
        
        print(f"Available Variables in {dataset_id}:")
        # ERDDAP 'info' JSON has 'Row Type' at index 0 and 'Variable Name' at index 1
        for row in rows:
            if row[0] == "variable":
                print(f"- {row[1]}")
                
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_dataset_variables()