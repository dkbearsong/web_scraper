import aiohttp
import os
from dotenv import load_dotenv
from typing import Iterable
import asyncio

# modules
from app.call_Ollama import OllamaClient
from app.postgres_mgr import PostgresManager

ws_micro_host = "http://localhost"
ws_micro_port = "5052"

load_dotenv()

class SQL_modder():
    def __init__(self, host: str = "localhost", port: str = "5432", user: str = "postgres", password: str = "", dbname: str = "postgres"):
        self.host = host
        self.port = port
        self.conn = PostgresManager(host, int(port), user, password, dbname=dbname)
        self.dbname = dbname

    def get_empty_locations(self):
        '''
        Returns a SQL query of offices where the city, state, and country are not loaded

        :param self: Description
        '''
        sql_statement = """
        SELECT id, location
        FROM office
        WHERE city IS NULL and state IS NULL and country IS NULL;
        """

        response = self.conn.execute_sql(sql_statement, fetch=True)
        # print(f"response: {response}")

        return response



    async def breakdown_location(self, location):
        '''
        Takes in location field and breaks it down into city, state, and country using AI

        :param self: Description

        input:
            location: ["id", "location"]
        '''
        system_prompt = '''
        You are tasked with breaking a location passed in into its country, it's state (if applicable), and its city. Only provide a state if the country is United States (USA). The input may provide a city, a country, several cities, or X locations with X being a count of possible locations.

        Rules:
        - Use abbreviations for countries commonly abbreviated, such as USA for United States or UK for United Kingdom
        - For cities in the USA, return the two letter abbreviation for the State. For cities outside of the United States, return NA for the state
        - If only a country is provided, return NA for the city and state
        - If no city or country is provided, return NA for city, state, and country
        - If multiple cities or locations are provided, return the details for the first city mentioned
        - Respond in JSON format only as shown in Output

        Output:
        {
            "city" : str,
            "state" : str,
            "country" : str
        }

        '''
        session = aiohttp.ClientSession()
        ollama = OllamaClient(session, "hf.co/bartowski/nvidia_Orchestrator-8B-GGUF:Q4_K_M", system_prompt)
        schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "state": {"type": "string"},
                "country": {"type":"string"}
            },
            "required": ["city", "state", "country"]
        }


        r_locations = []

        verify = False

        for i in location:
            id = i[0]
            prompt = i[1]
            response = await ollama.call(prompt, schema) # Makes initial call to Ollama
            count = 0
            # if response did not conform to the required schema, retry 5 times before erroring out.
            try:
                while verify == False:
                    if (response.get("city") is None or response.get("state") is None or response.get("country") is None) and count < 5:
                        count += 1
                        new_prompt =  f'''
                        The last response failed to meet the required JSON schema. Please rerun the below prompt, verifying the final result matches the outlined JSON schema:

                        {prompt}
                        '''
                        response = ollama.call(new_prompt, schema, temp=0.3, top_p=0.3, top_k=3)
                    elif count == 5:
                        raise ValueError(f"AI failed to return correctly formated response for id #{id}.")
                    else:
                        verify = True

            except ValueError as e:
                print(f"Received error: {e}")
            if verify == True:
                response['id'] = id
                r_locations.append(response)
            verify = False
            count = 0

        await ollama.unload()
        await ollama.session.close()

        return r_locations

    def update_db(self, vals:Iterable[dict]=None):
        '''
        Updates the office table in the database with the city, state, and country for the location.

        input:
            [
                {
                    "id": int,
                    "city": str,
                    "state": str,
                    "country": str
                }
            ]

        :param self: Description
        :param vals: Description
        :type vals: list[dict]
        '''
        query = '''
        UPDATE office
        SET city = %s, state = %s, country = %s
        WHERE id = %s;
        '''
        table = 'office'
        for i in vals:
            vals =  { "city": i['city'],"state": i['state'],"country": i['country']}
            where = { 'id': i['id'] }
            self.conn.update(table, vals, where)
        return

async def main():
    # Create Data Puller Object
    database = SQL_modder(
        dbname = os.getenv("DB_NAME", ""),
        user = os.getenv("DB_USER", ""),
        password = os.getenv("DB_PASSWORD", ""),
        host = os.getenv("DB_HOST", "localhost"),
        port = os.getenv("DB_PORT", "5432")
    )
    empty = database.get_empty_locations()
    print(f"number of offices with empty locations: {len(empty)}")
    breakdown_locations = await database.breakdown_location(empty)
    print(f"locations broken down: {len(breakdown_locations)}")
    database.update_db(breakdown_locations)
    print(f"all done updating city/state/country")


if __name__ == "__main__":
    asyncio.run(main())