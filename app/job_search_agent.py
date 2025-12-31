import json
import re
from dotenv import load_dotenv
import os
import aiohttp
import asyncio
from app.call_Ollama import OllamaClient

class JobSearchAgent:
    def __init__(self, client: OllamaClient):
        self.client = client

    @classmethod
    async def create(cls):
        """Async factory method for safe init"""
        SYSTEM_MESSAGE = """
                    You are an expert career coach reviewing the user's career experience and skills against a job title 
                    to determine if the job would be a good fit for the user.

                    For each request:
                    - You will receive ONE Criterion description, a Score Range, a Job Title, a Job History, and Skills.
                    - Input will be as shown below:
                        Job Title: <string>,
                        Job History: <list>,
                        Skills: <list>,
                        Criterion: <string>,
                        Score Range: <string>       
                    - Demonstrate careful analysis and consideration of multiple angles.
                    - Review the *Job Title* and the user's *Job History* and *Skills* closely against the *Criterion* before scoring
                     the job title.
                    - Be very harsh and critical in your analysis. If the job title matches the lower end of the criteria for scoring,
                     always err on the lower side. If the job title matches as described by the criteria, only then should you give it
                     a high score
                    - Score the title match 5 times, then return the average score.
                    - Score must be within the given *Score Range*.
                    - Output MUST be valid JSON, matching this schema exactly:
                    {
                        'criterion': <string>,
                        'score': <int>,        // out of max_score
                    }
                    - Double check your response. Verify it follows the output JSON format exactly. Verify you are including values 
                    for 'criterion' and for 'score'
                    """
        session = aiohttp.ClientSession()
        client = OllamaClient(session, model="gemma3:1b", system_message=SYSTEM_MESSAGE)
        return cls(client)

    async def title_review (self, jt, pt, sk):
        """
        Runs a series of Ollama calls to get a score for the job title

        Args:
        jt: Job Title, in the form of a string
        pt: Previous Title, an array of previous titles held by the user
        sk: Skills, an array of skills the user has

        Returns:
            int: score for the Job Title
        """
        bad_titles = json.loads(os.getenv("BAD_TITLES"))
        total_score = 100
        for b in bad_titles: # Deducts points to the total for title matches in bad_titles
            if re.search(b, jt):
                total_score -= 50
                break
        return total_score

    async def clear_ollama(self): # unloads the model from Ollama
        await self.client.unload()

    async def close(self):
        """Close aiohttp session when done"""
        await self.client.session.close()

async def main():
    load_dotenv()
    agent = await JobSearchAgent.create()
    #declare variables from .env
    job_title = 'AI Prompt Engineer'
    prev_titles = json.loads(os.getenv("PREV_TITLES"))
    skills = json.loads(os.getenv("SKILLS"))
    # starts reviewing process
    score_list = []
    count = 0
    while count < 10:
        count += 1
        try:
            ts = await agent.title_review(job_title, prev_titles, skills)
            score_list.append(ts)
        except Exception as e:
            print("❌ Error calling Ollama:", e)
        # unload Ollama model and close connection
    average = sum(score_list)/len(score_list)
    print(f"Average score: {average}")
    await agent.clear_ollama()
    await agent.close()
    return None


if __name__ == "__main__":
    asyncio.run(main())