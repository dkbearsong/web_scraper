import aiohttp
import json
import csv
import time
from random import random
from datetime import date
from collections import defaultdict

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
        self.dbname = dbname
        if self.conn.database_exists(self.dbname) == False:
            make_db()
            self.conn.connect(self.dbname)

    async def pull_data(self, source: str, payload: dict = {}) -> dict:
        rand_time = 3 * random()
        time.sleep(action.get('seconds', rand_time))
        url = f"{ws_micro_host}:{ws_micro_port}/{source}/scrape"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                data = await response.json()
                return data

    # Load list of sites to scrape

    def load_sites_list(self,sites_file: str) -> list:
        sites = defaultdict(list)
        with open(sites_file, "r") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                for key, value in row.items():
                    sites[key].append(value)
        return sites

    # Pull request payload from .site_strategies/{site}.json

    def load_site_strategies(self, path: str) -> list:
        print(path)
        with open(path, 'r') as f:
            site_strategies = json.load(f)
        return site_strategies

    # Load pulled data into database

    async def scrape_data(self,site:str,payload:dict, api_method:str="extract"):
        url = f"{ws_micro_host}:{ws_micro_port}/{api_method}"
        async with aiohttp.ClientSession() as session:
            # print(f"url: {url} | payload: {payload}")
            async with session.post(url, json=payload) as response:
                data = await response.json()
                return data

    def load_scraped_data_to_db(self, data: list):
        '''
        Load scraped data into PostgreSQL database
        input format:
            data = [
                {
                    "job_name": str,
                    "company": str,
                    "location": str,
                    "link": str,
                    "pay": str (optional)
                }
            ]
        '''
        
        for item in data:
            # Get or insert company
            companies = self.conn.search("company", {"company_name": item['company']})
            if companies:
                company_id = companies[0][0]
            else:
                result = self.conn.insert("company", {"company_name": item['company'], "company_url": item['company_url']}, returning=["id"])
                print(f"result: {result[0][0]}")
                company_id = result[0][0]

            # Get or insert office
            if item.get('location') == None: # Presuming that if a company does not list locations on their career page they are remote focused
                item['location'] = 'Remote'
            offices = self.conn.search("office", {"company_id": company_id, "location": item['location']})
            if offices:
                office_id = offices[0][0]
            else:
                result = self.conn.insert("office", {"company_id": company_id, "location": item['location']}, returning=["id"])
                office_id = result[0][0]

            # Check for duplicate job within 3 months
            query = """
            SELECT * FROM job 
            WHERE job_name = %s AND company_id = %s AND office_id = %s 
            AND date_added >= CURRENT_DATE - INTERVAL '3 months'
            """
            rows = self.conn.execute_sql(query, (item['title'], company_id, office_id), fetch=True)
            if rows:
                continue  # Skip duplicate
            
            # Insert job
            insert_data = {
                "job_name": item['title'], 
                "company_id": company_id, 
                "office_id": office_id, 
                "link": item['url'],
                "date_added": date.today()
            }

            if 'pay' in item:
                insert_data['pay'] = item['pay']

            self.conn.insert("job", insert_data)

        return

    def pull_data_db(self, query: str): # Need to modify this so it returns as a dict. Check 
        '''
        Allows running of database queries, specifically select statements to pull data

        input format:
            query = str (SQL select statement)
        returns: list of dicts
        '''
        rows = self.conn.execute_sql(query, fetch=True)
        return rows

    def insert_data_db(self, query: str, params: tuple = ()):
        self.conn.execute_sql(query, params)
        return

    def commit_data_db(self):
        # Note: PostgresManager commits automatically in execute_sql, but keeping for compatibility
        pass
        return

    def close_connection(self):
        self.conn.close()
        return
    
