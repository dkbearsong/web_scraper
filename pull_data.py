import requests
import json
import psycopg2
import asyncio

ws_micro = "http://localhost:5052"

async def pull_data(self, source: str = ws_micro, payload: dict = None) -> dict:
    async with requests.post(self.source + "/scrape", json=payload) as response:
        data = await response.json()
        return data

# Load list of sites to scrape

def load_sites_list(path: str) -> list:
    with open(path, 'r') as f:
        sites = json.load(f)
    return sites

# Pull request payload from .site_strategies/{site}.json

def load_site_strategies(path: str) -> list:
    with open(path, 'r') as f:
        site_strategies = json.load(f)
    return site_strategies



# Load pulled data into database

def load_data_to_db(data: dict, db_config: dict):
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
    conn = psycopg2.connect(
        dbname=db_config['dbname'],
        user=db_config['user'],
        password=db_config['password'],
        host=db_config['host'],
        port=db_config['port']
    )
    cursor = conn.cursor()
    
    for item in data:
        # Need checks for existing entries to avoid duplicates
        # Start with checking if job, company, and location exist as a record
        dup_record = cursor.execute(f"""
        SELECT job.job_name,company.company_name, office.city_name, office.state
        FROM job
        JOIN company ON company.id = job.company_id
        JOIN office on office.id = job.office_id
        WHERE job.job_name = {item['job_title']} AND company.company_name = {item['company']} AND office.city_name = {item['city']} AND office.state = {item['state']};
        """)
        if dup_record:
            continue  # Skip duplicate

        # If not, check if company exists, if not insert company
        company = cursor.execute(f"""
        SELECT id FROM company WHERE company_name = {item['company']};
        """)
        if not company:
            cursor.execute("""
            INSERT INTO company (company_name) VALUES (%s)
            """, (item['company'],))
            company_id = cursor.lastrowid

        # Then check if office record for company and location exists, if not insert office
        office = cursor.execute(f"""
        SELECT company.company_name, office.city_name, office.state
        FROM office 
        JOIN company ON company.id = office.company_id 
        WHERE company.company_name = {item['company']} AND office.city_name = {item['city']} AND office.state = {item['state']};
        """)
        if not office:
            cursor.execute("""
            INSERT INTO office (company_id, city_name, state) VALUES (%s, %s, %s)
            """, (company_id, item['city'], item['state']))
            office_id = cursor.lastrowid


        # Finally insert job record linked to company and office
        cursor.execute("""
        INSERT INTO jobs (job_title, company, location, link)
        VALUES (%s, %s, %s, %s)
        """, (item['job_title'], item['company'], item['location'], item['link']))

    conn.commit()
    cursor.close()
    conn.close()

    return



