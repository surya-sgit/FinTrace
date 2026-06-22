import httpx
import uuid
from datetime import date
import sys

def run_manual_test(jwt_token: str, portfolio_id: str, target_date: str):
    """
    Manually tests the Advanced Analytics Performance Attribution endpoint.
    Assumes your FastAPI server is running on http://localhost:8000
    """
    print(f"Testing Analytics Engine against Portfolio {portfolio_id} for date {target_date}...")
    
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    url = f"http://localhost:8000/api/v1/analytics/{portfolio_id}/attribution"
    params = {
        "target_date": target_date
    }

    try:
        response = httpx.get(url, headers=headers, params=params)
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCCESS! Attribution Profile:")
            print(f"- Analysis Date: {data.get('analysis_date')}")
            print(f"- Primary Drag: {data.get('primary_drag_ticker')}")
            print(f"- Absolute Impact: {data.get('absolute_impact')}")
            print("\nFull Contribution Matrix:")
            for item in data.get('full_contribution_matrix', []):
                print(f"  > {item['ticker']} | Net: {item['net_contribution']} | Legacy Drift: {item['legacy_drift']} | Intraday: {item['intraday_impact']} | Shield: {item['corporate_shield']}")
        else:
            print("\n❌ FAILED / REJECTED:")
            print(response.json())
            
    except Exception as e:
        print(f"Connection failed. Is the server running? Error: {e}")

if __name__ == "__main__":
    print("=== FinTrace Analytics Manual Test ===")
    token = input("Enter your valid JWT Bearer Token: ").strip()
    pid = input("Enter a valid Portfolio ID (UUID): ").strip()
    td = input("Enter target date (YYYY-MM-DD, e.g., 2024-01-15): ").strip()
    
    if token and pid and td:
        run_manual_test(token, pid, td)
    else:
        print("Missing required inputs.")
