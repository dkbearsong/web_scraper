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
                    - You will receive a Job Title, a Job History, and Skills.
                    - Input will be as shown below:
                        Job Title: <string>,
                        Job History: <list>,
                        Skills: <list>,
                    - Demonstrate careful analysis and consideration of multiple angles.
                    - Review the *Job Title* and the user's *Job History* and *Skills* closely before scoring the job title.
                    - Score how well the job title matches the user's experience and skills on a scale of 1 to 100, where 1 is a poor match and 100 is an excellent match.
                    - Score the title match 5 times, then return the average score.
                    - Output MUST be valid JSON, matching this schema exactly:
                    {
                        'score': <int>,
                    }
                    - Double check your response. Verify it follows the output JSON format exactly. Verify you are including values for 'criterion' and for 'score'
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
        json_schema = {
            "type": "object",
            "properties": {
                "score": {"type": "number"}
            },
            "required": "score"
        }
        
        valid = False
        user_prompt = f"""
        User Input:
        Job Title: { jt }
        Job History: { pt } 
        Skills: { sk } 
        Return JSON only.
        """
        invalid = False
        invalid_count = 0
        score = 0
        bad_titles = json.loads(os.getenv("BAD_TITLES"))

        while not valid: # Verifies the reply contained good data. If not tries again
            if not invalid:
                result = await self.client.call(user_prompt, json_schema, 0.2, 0.5, 5, mt=1024)
                print(f"Response received: {result}")
            else:
                print("Invalid response, retrying...")
                result = await self.client.call(f"The previous response did not match the outlined criteria for JSON formatting. Retry the response following the JSON schema outlined in the system message." + user_prompt, json_schema, 0.7, 0.7, 15, mt=1024)

            try:
                if (isinstance(result.get('score'), int) or isinstance(result.get('final_score'), int)):
                    print("Valid format." + str(result))
                    valid = True
                    score = int(result.get('score') if 'score' in result else result.get('final_score'))
                    for b in bad_titles: # Deducts points to the total for title matches in bad_titles
                        if re.search(b, jt):
                            score -= 50
                            break
                else:
                    print("Invalid format." + str(result))
                    invalid = True
                    invalid_count += 1
                    if invalid_count > 3:
                        print("Too many invalid responses, ending review and continuing on to next job.")
                        valid = True
                        invalid_count = 0
            except KeyError as e:
                print(e)
                print("KeyError, retrying...")
                continue
        return score

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