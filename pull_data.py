import aiohttp
import json
import psycopg2
import csv
import requests

ws_micro_host = "http://localhost"
ws_micro_port = "5052"

class DataPuller:
    def __init__(self, host: str = ws_micro_host, port: str = ws_micro_port, db_config: dict = {}):
        self.host = host
        self.port = port
        self.conn = psycopg2.connect(
            dbname=db_config['dbname'],
            user=db_config['user'],
            password=db_config['password'],
            host=self.host,
            port=self.port
        )
        self.cursor = self.conn.cursor()

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
                    "job_title": str}
                    "company": str,
                    "city": str,
                    "state": str,
                    "link": str
                }
            ]
            db_config = {
                'dbname': str,
                'user': str,
                'password': str,
                'host': str,
                'port': int
            }
        '''
        
        for item in data:
            # Need checks for existing entries to avoid duplicates
            # Start with checking if job, company, and location exist as a record
            dup_record = self.cursor.execute(f"""
            SELECT job.job_name,company.company_name, office.location
            FROM job
            JOIN company ON company.id = job.company_id
            JOIN office on office.id = job.office_id
            WHERE job.job_name = {item['job_title']} AND company.company_name = {item['company']} AND office.location = {item['location']};
            """)

            if dup_record:
                continue  # Skip duplicate

            # If not, check if company exists, if not insert company
            company = self.cursor.execute(f"""
            SELECT id FROM company WHERE company_name = {item['company']};
            """)

            if not company:
                self.cursor.execute("""
                INSERT INTO company (company_name) VALUES (%s)
                """, (item['company'],))
                company_id = self.cursor.lastrowid

            # Then check if office record for company and location exists, if not insert office
            office = self.cursor.execute(f"""
            SELECT company.company_name, office.city_name, office.state
            FROM office 
            JOIN company ON company.id = office.company_id 
            WHERE company.company_name = {item['company']} AND office.location = {item['location']};
            """)
            if not office:
                self.cursor.execute("""
                INSERT INTO office (company_id, location) VALUES (%s, %s, %s)
                """, (company_id, item['location']))
                office_id = self.cursor.lastrowid


            # Finally insert job record linked to company and office
            self.cursor.execute("""
            INSERT INTO jobs (job_title, company, location, link)
            VALUES (%s, %s, %s, %s)
            """, (item['job_title'], item['company'], item['location'], item['link']))

        self.conn.commit()

        return

    async def pull_data_DB (self, query: str = "") -> dict:
        '''
        Allows running of database queries, specifically select statements to pull data

        input format:
            source = str (name of microservice)
            query = str (SQL select statement)
        '''
        response = await self.cursor.execute(query) # type: ignore
        return response.json()

    def close_connection(self):
        self.cursor.close()
        self.conn.close()
        return
    
