from pymongo import MongoClient
from dotenv import load_dotenv
import certifi
import os
from datetime import datetime, timedelta, timezone
import aiohttp
import asyncio
import pytz
import ssl

# Load environment variables from .env file
load_dotenv()
ca = certifi.where()
client = MongoClient(os.getenv("MONGO_DB_URI"), tlsCAFile=ca)
db = client["league_discord_bot"]


# Object for handling rate limits, mainly for communicating with Riot's API.
# Keeps track of how many calls have been made over a certain period and
# sleeps for necessary time when max calls is reached.
class AsyncRateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
    
    async def wait(self):
        now = datetime.now()
        
        # Remove calls that are outside of the current period
        self.calls = [call for call in self.calls if now - call < timedelta(seconds=self.period)]
        
        if len(self.calls) >= self.max_calls:
            # Calculate the time to sleep
            oldest_call = min(self.calls)
            sleep_time = (oldest_call + timedelta(seconds=self.period)) - now
            print(f"Rate limit almost reached. Sleeping for {sleep_time.total_seconds()} seconds")
            await asyncio.sleep(sleep_time.total_seconds())
        
        # Record the current call
        self.calls.append(datetime.now())


# Handler function for all API calls made
# Contains error handling and backup rate limit handling
async def handle_api_call(url):
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, ssl=ssl_context) as response:
                if response.status == 429:  # Rate limit exceeded
                    retry_after = int(response.headers.get("Retry-After", 1))
                    print(f"Rate limit exceeded. Retrying in {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                    return await handle_api_call(url)  # Retry the request
                response.raise_for_status()  # Raise an exception for non-200 status codes
                data = await response.json()
                return data
        except aiohttp.ClientResponseError as e:
            print(f"Error in API call: {e.status}, message='{e.message}'")
            return None


# Returns a list of all summoners in a given Guild (discord server)
async def get_summoners(guild_id):
    collection = db.discord_servers
    document = collection.find_one({"guild_id": guild_id})

    if document and "summoners" in document:
        summoners_list = document["summoners"]
        return summoners_list

    return None


# Returns a list of all guilds stored within Scuttle's database
async def get_guilds():
    collection = db.discord_servers
    documents = collection.find()

    if not documents:
        print("No documents found in discord_servers.")
    else:
        return list(documents)


# Handler function to run script once every hour on the hour
async def run_at_start_of_next_hour():
    while True:
        # Calculate seconds until the next hour
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        wait_seconds = (next_hour - now).total_seconds()

        # Wait until the start of the next hour
        print(f"Waiting {next_hour - now} until the next hour.")
        await asyncio.sleep(wait_seconds)

        # Run the main function
        guilds = await get_guilds()
        await cache_match_data(guilds)

        await asyncio.sleep(10)


# Updates summoner's last time cached data in database
async def update_cached_data_timestamp(summoner):
    collection = db.cached_match_data_timestamps
    now = datetime.now(pytz.utc)

    query = {'puuid': summoner["puuid"]}
    update = {
        '$set': {
            'last_cached': now,
        },
        '$setOnInsert': {
            'name': summoner["name"], # Set 'name' only if inserting a new document
            'puuid': summoner["puuid"], # Set 'puuid' only if inserting a new document
        }
    }

    result = collection.update_one(query, update, upsert=True)
                                   
    if result.upserted_id is not None:
        print(f'Inserted a new last_cached document for {summoner["name"]}')
    else:
        print(f'Modified last_cached document for {summoner["name"]}')


# Checks if summoner's match history has already been cached within range
async def check_if_cached_within_range(summoner, range=1):
    collection = db.cached_match_data_timestamps
    now = datetime.now(timezone.utc)
    lower_range = now - timedelta(days=range)
    

    document = collection.find_one({"puuid": summoner["puuid"]})

    if not document:
        print(f"{summoner["name"]} has no last cached data.")
    else:
        last_cached_date = document["last_cached"]
        last_cached_date = pytz.utc.localize(last_cached_date)

        if lower_range < last_cached_date < now:
            print(f"{summoner["name"]}'s match data has been cached within the last {range} days.")
            return True
        
    return False


# Removes extra participants data from match
# This way each document in collection will contain summoner puuid and their individual performance
def process_match_data(summoner_puuid, match_data):
    processed_match_data = match_data.copy()

    filtered_participants = [item for item in processed_match_data["info"]["participants"] if item['puuid'] == summoner_puuid]
    processed_match_data["info"]["participants"] = filtered_participants
    processed_match_data["summoner_puuid"] = summoner_puuid

    return processed_match_data


def get_area_from_region(region): 
    americas = ["br1", "la1","la2","na1"]
    asia = ["jp1", "kr"]
    europe = ["euw1", "eun1", "tr1", "ru"]
    sea = ["oc1", "ph2", "sg2", "th2", "tw2", "vn2"]

    if region in americas:
        return "americas"
    elif region in asia:
        return "asia"
    elif region in europe:
        return "europe"
    elif region in sea:
        return "sea"


# Fetches and caches all match history for all summoner's in Scuttle's database
# Stores the last 30 days worth of match data for all summoners
async def cache_match_data(guilds):
    rate_limiter = AsyncRateLimiter(29999, 600)
    collection = db.cached_match_data
    summoners_checked = []
    num_total_matches_cached = 0

    job_start_time = datetime.now()
    formatted_job_start_time = job_start_time.strftime("%m/%d/%y %H:%M:%S")

    print(f"Caching all data from the last 30 days (Started at {formatted_job_start_time})...")

    for guild in guilds:
        summoners = await get_summoners(guild["guild_id"])
        if(summoners):
            for summoner in summoners:
                try:
                    if summoner not in summoners_checked:
                        matches_cached = 0
                        days_fetched = 0
                        days_to_fetch_max = 30
                        summoner_puuid = summoner["puuid"]

                        # check if summoner's data has been cached within the past day
                        # if so, only fetch data for the past day
                        was_cached_within_past_day = await check_if_cached_within_range(summoner, 1)
                        if was_cached_within_past_day:
                            days_to_fetch_max = 1

                        while days_fetched < days_to_fetch_max:
                            days_to_fetch = min(5, days_to_fetch_max - days_fetched)
                            end_time = datetime.today() - timedelta(days=days_fetched)
                            start_time = end_time - timedelta(days=days_to_fetch)
                            end_timestamp = int(end_time.timestamp())
                            start_timestamp = int(start_time.timestamp())
                            
                            print(f"Fetching matches from {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')} for summoner {summoner["name"]}.")

                            if "region" in summoner:
                                area = get_area_from_region(summoner["region"])
                            else:
                                area = "americas"

                            url = f"https://{area}.api.riotgames.com/lol/match/v5/matches/by-puuid/{summoner_puuid}/ids?startTime={start_timestamp}&endTime={end_timestamp}&queue=420&start=0&count=100&api_key={os.getenv('RIOT_API_KEY')}"
                            await rate_limiter.wait()
                            match_ids = await handle_api_call(url)

                            # Find documents where `metadata.matchId` is in list of match IDs
                            matched_documents = collection.find({"metadata.matchId": {"$in": match_ids}, "summoner_puuid": summoner_puuid})

                            # Extract the matched IDs
                            matched_ids = [doc['metadata']['matchId'] for doc in matched_documents]

                            # Filter your list to remove the matched IDs
                            unmatched_ids = [mid for mid in match_ids if mid not in matched_ids]

                            print(f"Matches already cached: {matched_ids}")
                            print(f"Matches being cached: {unmatched_ids}")

                            if unmatched_ids:
                                for match_id in unmatched_ids:
                                    match_url = f"https://{area}.api.riotgames.com/lol/match/v5/matches/{match_id}?api_key={os.getenv('RIOT_API_KEY')}"
                                    await rate_limiter.wait()
                                    single_match_data = await handle_api_call(match_url)

                                    if single_match_data:
                                        matches_cached += 1
                                        num_total_matches_cached += 1
                                        processed_match_data = process_match_data(summoner_puuid, match_data=single_match_data) 
                                        collection.insert_one(processed_match_data)

                            if "region" in summoner:
                                print(f"Pulled matches from '{area}' area for summer from {summoner["region"]} region")

                            days_fetched += days_to_fetch
                        
                        summoners_checked.append(summoner)
                        await update_cached_data_timestamp(summoner)
                        print(f"{matches_cached} matches cached.")
                    else:
                        print(f"Already iterated through summoner {summoner["name"]}")
                except:
                    print(f"An error has occured for summoner {summoner["name"]} with region {summoner["region"]}")
        else:
            print(f"Guild {guild["name"]} does not have any summoners. Skipping.")

    print(f"\n{num_total_matches_cached} matches cached into cached_matches_data collection.")
    job_end_time = datetime.now()
    elapsed_time = job_end_time - job_start_time
    elapsed_time_seconds = int(elapsed_time.total_seconds())
    hours = elapsed_time_seconds // 3600
    minutes = (elapsed_time_seconds % 3600) // 60
    seconds = elapsed_time_seconds % 60
    formatted_elapsed_time = f"{hours:02}:{minutes:02}:{seconds:02}"
    print(f"Done caching all match data from the last 30 days. Took {formatted_elapsed_time}")

if __name__ == "__main__":
    guilds = asyncio.run(get_guilds())
    asyncio.run(cache_match_data(guilds))
    asyncio.run(run_at_start_of_next_hour())
