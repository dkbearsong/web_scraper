import aiohttp
import json
import csv
import requests

# Modules
from app.postgres_mgr import PostgresManager
from app.make_db import make_db

ws_micro_host = "http://localhost"
ws_micro_port = "5052"

class DataPuller:
    def __init__(self, host: str = "localhost", port: str = "5432", user: str = "postgres", password: str = "", dbname: str = "postgres"):
        self.host = host
        self.port = port
        self.conn = PostgresManager(host, int(port), user, password, dbname=dbname)

    async def pull_data(self, source: str, payload: dict = {}) -> dict:
        url = f"{self.host}:{self.port}/{source}/scrape"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                data = await response.json()
                return data
            data = await response.json()
            return data

    # Load list of sites to scrape

    def load_sites_list(self,sites_file: str) -> list:
        with open(sites_file, "r") as csvfile:
            reader = csv.reader(csvfile)
            sites = list(reader)
        return sites

    # Pull request payload from .site_strategies/{site}.json

    def load_site_strategies(self, path: str) -> list:
        with open(path, 'r') as f:
            site_strategies = json.load(f)
        return site_strategies

    # Load pulled data into database

    async def scrape_data(self,site:str,payload:dict):
        response_data = await requests.post(site, data=payload) # type: ignore
        return response_data

    def load_scraped_data_to_db(self, data: list):
        '''
        Load scraped data into PostgreSQL database
        input format:
            data = [
                {
                    "job_title": str,
                    "company": str,
                    "location": str,
                    "link": str
                }
            ]
        '''
        
        for item in data:
            # Get or insert company
            companies = self.conn.search("company", {"company_name": item['company']})
            if companies:
                company_id = companies[0][0]
            else:
                result = self.conn.insert("company", {"company_name": item['company']}, returning=["id"])
                company_id = result[0][0]

            # Get or insert office
            offices = self.conn.search("office", {"company_id": company_id, "location": item['location']})
            if offices:
                office_id = offices[0][0]
            else:
                result = self.conn.insert("office", {"company_id": company_id, "location": item['location']}, returning=["id"])
                office_id = result[0][0]

            # Check for duplicate job within 3 months
            query = """
            SELECT 1 FROM job 
            WHERE job_title = %s AND company_id = %s AND office_id = %s 
            AND date_added >= CURRENT_DATE - INTERVAL '3 months'
            """
            rows = self.conn.execute_sql(query, (item['job_title'], company_id, office_id), fetch=True)
            if rows:
                continue  # Skip duplicate

            # Insert job
            self.conn.insert("job", {
                "job_title": item['job_title'], 
                "company_id": company_id, 
                "office_id": office_id, 
                "link": item['link']
            })

        return

    def pull_data_db(self, query: str):
        '''
        Allows running of database queries, specifically select statements to pull data

        input format:
            query = str (SQL select statement)
        returns: list of tuples
        '''
        rows = self.conn.execute_sql(query, fetch=True)
        return rows

    def insert_data_db(self, query: str):
        self.conn.execute_sql(query)
        return

    def commit_data_db(self):
        # Note: PostgresManager commits automatically in execute_sql, but keeping for compatibility
        pass
        return

    def close_connection(self):
        self.conn.close()
        return
    
