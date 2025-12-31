import os
from dotenv import load_dotenv
import json
from docx import Document
import asyncio

# Modules
from pull_data import DataPuller
from app.job_search_agent import JobSearchAgent
from app.job_summary_review_agent import JobSumReviewAgent

load_dotenv()

#==================== Helper Functions ====================

# Previous Titles, skills, and resume
def load_resume_as_text():
    # doc = Document(input("Provide the path for the resume file to use: "))
    doc = Document(os.getenv("RESUME"))
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text.strip())
    return full_text

#==================== AI Functions ========================

# Call on Ollama. Send with system message to rate the job title and return that back with a score in JSON format
async def job_title_score(client, jt, pt, sk):
    job_title = jt
    # print("Job title: " + job_title + "\nPrevious Titles: " + str(pt) + "\nSkills: " + str(sk))
    try:
        ts = await client.title_review(job_title, pt, sk)
        return ts
    except Exception as e:
        print("❌ Error calling Ollama:", e)

# Call on Ollama. Send with system message to rate the job title and return that back with a score in JSON format
async def job_summary_score(client, js, res):
    job_summary = js
    'try:'
    jsum = await client.summary_review(job_summary, res)
    return jsum
    """except Exception as e:
        print("❌ Error calling Ollama:", e)"""

#==================== Job Scraper =========================

async def main():
    # Load .env variables
    prev_titles = json.loads(os.getenv("PREV_TITLES", "[]"))
    skills = json.loads(os.getenv("SKILLS", "[]"))
    resume = load_resume_as_text()

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
        SELECT id, job_name
        FROM job
        WHERE title_rating IS EMPTY AND skip IS NOT True;
        ''',
        'scrape_summaries': f'''
        SELECT j.id,j.link, c.company_name AS company
        FROM job j
        JOIN company c ON j.company_id = c.id
        WHERE title_rating >= 80 AND skip IS NOT True AND job_summary IS empty;
        ''',
        'scrape_sum_companies': f'''
        SELECT DISTINCT c.company_name AS company
        FROM company c
        JOIN job j ON j.company_id = c.id
        WHERE title_rating >= 80 AND skip IS NOT True AND job_summary IS empty;
        ''',
        'unranked_summaries': f'''
        SELECT id, job_summary
        FROM job
        WHERE title_rating >= 80 AND skip IS NOT True AND job_summary IS NOT empty and summary_rating IS empty;
        '''
    }

    # Get unranked titles
    titles_to_process = dp.pull_data_DB(sql_read_queries['unranked_titles'])

    # Run AI over unranked titles, or just score them
    score_list = []
    agent = await JobSearchAgent.create()
    for i in titles_to_process:
        score_list.append({
            'id': i['id'],
            'score': await job_title_score(agent, i['job_name'], prev_titles, skills) # Need to check what data type this returns
        })

    # Update the titles with the title rankings
    for i in score_list:
        query = f'''
        UPDATE job 
        SET job_score = {i['score']}
        WHERE id = {i['id']}   
        '''
        dp.insert_data_db(query)
    dp.commit_data_db()

    # unload Ollama model and close connection
    await agent.clear_ollama()
    await agent.close()

    # Scrape the summaries for the jobs above 80 score and update them
    # I need new strategies for how to pull the job descriptions based on the site link

    scrape_sum_list = dp.pull_data_DB(sql_read_queries['scrape_summaries']) #presuming data in list
    s_companies =  dp.pull_data_DB(sql_read_queries['scrape_sum_companies']) # scraped companies, pulls from similar query to scrape_sum_list to get the specific companies in order to identify how to scrape that companies job posting

    # Pull in the site strategies based on the sites pulled from the sites file
    site_strategies = {}
    data = []
    for i in s_companies:
        strategy = dp.load_site_strategies(i)
        site_strategies[i] = strategy

    for i in scrape_sum_list:
        job_description = {
            'id': i['id'],
            'summary': dp.scrape_data(i['site'], site_strategies[i['company']])
        }
        data.append(job_description)

    for i in data:
        query = f'''
        UPDATE job
        SET title_summary = {i['summary']}
        WHERE job_id = {i['job_id']}
        '''
        dp.insert_data_db(query)
    dp.commit_data_db()

    del titles_to_process, score_list, scrape_sum_list, s_companies, strategy, site_strategies, data, query
    """
    # Get the unranked summaries
    summaries_to_process = dp.pull_data_DB(sql_read_queries['unranked_summaries'])

    # Run AI over the unranked summaries
    agent = await JobSumReviewAgent.create()
    score_list = []

    for i in summaries_to_process:
        score_list.append({
            'id': i['id'],
            'score': await job_summary_score(agent, i['job_summary'].split('.'), resume)
        })

    # Update the scores for the unranked summaries

    for i in score_list:
        query = f'''
        UPDATE job 
        SET summary_rating = {i['score'][0]}
        SET jsr_reasoning = {i['score'][1]} 
        WHERE id = {i['id']}   
        '''
        dp.insert_data_db(query)
    dp.commit_data_db()

    """

    return

if __name__ == "__main__":
    asyncio.run(main())

