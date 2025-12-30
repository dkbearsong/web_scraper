import os
import csv
from dotenv import load_dotenv

# Modules
from pull_data import DataPuller

load_dotenv()

#==================== Job Scraper ====================

def main():
    # Create Data Puller Object
    dp = DataPuller(
        db_config={
            'dbname': os.getenv("DBNAME", ""),
            'user': os.getenv("USER", ""),
            'password': os.getenv("PASSWORD","")
        }
    )
    
    # Get sites file from .env and pulls the sites in. Needs to be a csv set up with name and site columns
    sites_file = os.getenv("SITES","")
    sites = dp.load_sites_list(sites_file)

    # Pull in the site strategies based on the sites pulled from the sites file
    site_strategies = []
    data = []
    for i in sites:
        strategy = { 
            "company": i['name'],
            "site": i['site'],
            "strategy": dp.load_site_strategies(i['name'])
        }
        site_strategies.append(strategy)

    # Scrape the jobs from the sites using the link to the sites and the attached strategy
    for i in site_strategies:
       pulled_data = {"company": i['company'], "data":dp.scrape_data(i['site'], i['strategy'])}
       for j in pulled_data['data']:
           if j:
            data.append({
                "company": i['company'],
                "title": j['title'],
                "url": j['link'],
                "location": j['location']
                })
            
    # Load in the latest pulled in jobs
    dp.load_scraped_data_to_db(data)
    
    # clear variables from data

    del data, site_strategies, sites, sites_file, strategy, pulled_data

    # build SQL queries
    sql_read_queries = {
        'unranked_titles' : f'''
        SELECT id, job_name, link
        FROM job
        WHERE title_rating IS EMPTY AND skip IS NOT True;
        ''',
        'scrape_summaries': f'''
        SELECT id,link
        FROM job
        WHERE title_rating >= 80 AND skip IS NOT True AND job_summary IS empty;
        ''',
        'unranked_summaries': f'''
        SELECT id, job_name, link, job_summary
        FROM job
        WHERE title_rating >= 80 AND skip IS NOT True AND job_summary IS NOT empty and summary_rating IS empty;
        '''
    }

    # Get unranked titles
    titles_to_process = dp.pull_data_DB(sql_read_queries['unranked_titles'])

    # Run AI over unranked titles, or just score them
    # Update the titles with the title rankings
    # Scrape the summaries for the jobs above 80 score and update them
    # Get the unranked summaries
    # Run AI over the unranked summaries
    # Update the scores for the unranked summaries



    

    

if __name__ == "__main__":
    main()

