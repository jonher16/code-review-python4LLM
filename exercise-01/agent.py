# agent.py  (BAD VERSION)
import os, requests, json, time

CACHE = {}
MISTRAL_URL = "https://api.example-llm.com/v1/chat/completions"
API_KEY = "dev-key-123"
RETRIES = 5
DEBUG = True

def get_llm_answer(prompt, model="mistral-tiny", temperature=0.7, tools=None):
    
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature}
    if tools:
        payload["tools"] = tools

    headers = {"Authorization": "Bearer " + API_KEY}
    r = requests.post(MISTRAL_URL, headers=headers, data=json.dumps(payload))
    try:
        return r.json()["choices"][0]["message"]["content"]
    except:
        return r.text

def get_weather_from_api(city, units="metric"):

    url = "http://api.weather.internal/current?city=" + city + "&units=" + units
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.json()
    else:
        return {"temp": "??", "desc": "unknown"}

def answer_city_weather(city, units="metric", use_cache=True):
   
    if use_cache and city in CACHE:
        ts, txt = CACHE[city]
        if time.time() - ts < 60:
            if DEBUG: print("cache hit")
            return txt

    w = get_weather_from_api(city, units)
    temp = w.get("temp")
    desc = w.get("desc", "clear")
    prompt = f"User asked: What's the weather in {city}? Data says temp={temp}, desc={desc}. Answer nicely."

    tries = 0
    while tries < RETRIES:
        try:
            txt = get_llm_answer(prompt)
            break
        except Exception as e:
            if DEBUG: print("err:", e)
            tries += 1
            time.sleep(0.1)
            txt = "temporary error"
    CACHE[city] = (time.time(), txt)
    return txt

def handler(event):

    city = event.get("query",{}).get("city")
    if not city:
        return {"status": 400, "body": "missing city"}
    units = event.get("query",{}).get("units","metric")
    body = answer_city_weather(city, units)
    if DEBUG: print("resp:", body)
    return {"status": 200, "body": body}

if __name__ == "__main__":
    print(handler({"query":{"city":"Istanbul"}}))
