import streamlit as st
import pandas as pd
import requests
from rapidfuzz import fuzz
import json
import os

# ===========================
# Load API Key
# ===========================
with open("config.json") as f:
    config = json.load(f)
API_KEY = config["api_key"]

DEFAULT_IMAGE = "https://via.placeholder.com/200x140.png?text=No+Image"

# ===========================
# Load Preprocessed Dataset
# ===========================
@st.cache_data
def load_recipes():
    with open("recipes_25k.pkl", "rb") as f:
        recipes = pd.read_pickle(f)
    return recipes

recipes_df = load_recipes()

# ===========================
# Ingredient Synonyms
# ===========================
ingredient_synonyms = {
    "bhindi": "okra", "ghee": "clarified butter", "idli rice": "parboiled rice",
    "paneer": "cottage cheese", "panner": "cottage cheese", "malai": "cream",
    "curd": "yogurt", "dahi": "yogurt", "jaggery": "unrefined cane sugar",
    "imli": "tamarind", "til": "sesame", "rajma": "kidney beans",
    "lobia": "black eyed peas", "chole": "chickpeas", "soya chunks": "textured vegetable protein",
    "rava": "semolina", "suji": "semolina", "atta": "wheat flour",
    "maida": "all-purpose flour", "besan": "gram flour", "sabudana": "tapioca pearls",
    "poha": "flattened rice", "haldi": "turmeric", "adrak": "ginger",
    "lasun": "garlic", "mirchi": "chili", "drumstick": "moringa",
    "tofu": "soy paneer", "jeera": "cumin", "methi": "fenugreek",
    "pulao": "fried rice", "kachumber": "salad", "dal": "lentils", "roti": "flatbread"
}

def normalize_ingredient(ing: str) -> str:
    ing = ing.lower().strip()
    return ingredient_synonyms.get(ing, ing)

# ===========================
# Taste Memory Functions
# ===========================
TASTE_FILE = "taste_memory.json"

def load_user_taste():
    if os.path.exists(TASTE_FILE):
        with open(TASTE_FILE, "r") as f:
            return json.load(f)
    return {"liked": []}

def save_user_taste(data):
    with open(TASTE_FILE, "w") as f:
        json.dump(data, f, indent=4)

if "user_taste" not in st.session_state:
    st.session_state.user_taste = load_user_taste()

# ===========================
# Spoonacular API (Primary)
# ===========================
def get_recipes_from_api(ingredients, diet="None"):
    try:
        url = "https://api.spoonacular.com/recipes/complexSearch"
        params = {
            "apiKey": API_KEY,
            "includeIngredients": ingredients,
            "number": 10,
            "addRecipeInformation": True
        }
        if diet != "None":
            params["diet"] = diet.lower()
        r = requests.get(url, params=params)
        if r.status_code != 200:
            return []
        data = r.json()
        if "results" not in data or not data["results"]:
            return []
        recipes = []
        for x in data["results"]:
            recipes.append({
                "title": x.get("title"),
                "readyInMinutes": x.get("readyInMinutes", "N/A"),
                "servings": x.get("servings", "N/A"),
                "sourceUrl": x.get("sourceUrl", "#"),
                "image": x.get("image", DEFAULT_IMAGE),
                "cuisines": ", ".join(x.get("cuisines", [])) or "Not specified",
                "nutrition": "N/A",
                "ingredients": []
            })
        return recipes
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

# ===========================
# Google Search Fallback
# ===========================
def google_search_link(recipe_name):
    """Generate a Google search link for recipe instructions."""
    query = recipe_name.replace(" ", "+") + "+recipe"
    return f"https://www.google.com/search?q={query}"

# ===========================
# Enrich Offline Recipe (Optional)
# ===========================
def enrich_offline_recipe(recipe_name):
    try:
        url = "https://api.spoonacular.com/recipes/complexSearch"
        params = {
            "apiKey": API_KEY,
            "query": recipe_name,
            "addRecipeInformation": True,
            "number": 1
        }
        r = requests.get(url, params=params)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("results"):
            return None
        x = data["results"][0]
        return {
            "title": x.get("title", recipe_name),
            "readyInMinutes": x.get("readyInMinutes", "N/A"),
            "servings": x.get("servings", "N/A"),
            "cuisines": ", ".join(x.get("cuisines", [])) or "Not specified",
            "nutrition": "N/A",
            "image": x.get("image", DEFAULT_IMAGE),
            "sourceUrl": x.get("sourceUrl", "#"),
            "ingredients": []
        }
    except Exception as e:
        print(f"Offline enrichment error: {e}")
        return None

# ===========================
# Offline Smart Search
# ===========================
def search_offline_recipes(user_input, user_taste):
    ingredients = [normalize_ingredient(i) for i in user_input.split(",")]
    results = []
    liked_ings = [normalize_ingredient(i) for recipe in user_taste["liked"] for i in recipe.get("ingredients", [])]

    for idx, row in recipes_df.iterrows():
        recipe_ings = [normalize_ingredient(i) for i in row["ingredients"]]
        exact = sum(1 for ing in ingredients if ing in recipe_ings)
        partial = sum(1 for ing in ingredients if any(fuzz.partial_ratio(ing, r_ing) > 75 for r_ing in recipe_ings))
        taste_bonus = sum(1 for ing in recipe_ings if ing in liked_ings)
        score = exact * 2 + partial + taste_bonus * 0.5
        if score > 0:
            results.append((idx, score))

    if not results:
        return pd.DataFrame()
    top = sorted(results, key=lambda x: x[1], reverse=True)[:20]
    df = recipes_df.loc[[i for i, _ in top]].copy()
    df["Match Score"] = [s for _, s in top]
    return df[["title", "ingredients", "Match Score"]]

# ===========================
# UI Styling
# ===========================
st.set_page_config(page_title="Smart Recipe Finder", page_icon="🍴", layout="wide")
st.markdown("""
<style>
.stApp {
    background-image: url("https://4kwallpapers.com/images/wallpapers/ios-13-stock-ipados-dark-green-black-background-amoled-ipad-2560x1440-794.jpg");
    background-size: cover;
    background-attachment: fixed;
}
.recipe-card {
    background-color: rgba(255,255,255,0.1);
    padding: 1em;
    border-radius: 12px;
    margin-bottom: 1em;
    box-shadow: 0px 4px 10px rgba(0,0,0,0.4);
    text-align: center;
}
.recipe-img {
    border-radius: 10px;
    width: 200px;
    height: 140px;
    object-fit: cover;
    margin-bottom: 8px;
}
.recipe-title {
    font-size: 1.1em;
    font-weight: 600;
    color: #00ffcc;
}
.recipe-meta {
    color: #ddd;
    font-size: 0.9em;
}
</style>
""", unsafe_allow_html=True)

st.title("🍴 Smart Recipe Finder")
tab1, tab2 = st.tabs(["🔍 Find Recipes", "❤️ Liked Recipes"])

# -------------------- TAB 1 --------------------
with tab1:
    ingredients = st.text_input("Enter ingredients (comma-separated):")
    diet = st.selectbox("Dietary preference:", ["None", "Vegetarian", "Vegan", "Gluten-Free", "Ketogenic"])

    if "search_results" not in st.session_state:
        st.session_state.search_results = None
        st.session_state.search_mode = None

    if st.button("Find Recipes"):
        if ingredients:
            with st.spinner("Searching recipes..."):
                api_results = get_recipes_from_api(ingredients, diet)
                if api_results:
                    st.session_state.search_results = api_results
                    st.session_state.search_mode = "api"
                else:
                    offline = search_offline_recipes(ingredients, st.session_state.user_taste)
                    st.session_state.search_results = offline
                    st.session_state.search_mode = "offline"
        else:
            st.warning("Please enter some ingredients.")

    # Display Search Results
    if st.session_state.search_results is not None:
        if st.session_state.search_mode == "api":
            st.subheader("🌐 Recipes from Spoonacular API")
            cols = st.columns(2)
            for i, r in enumerate(st.session_state.search_results):
                with cols[i % 2]:
                    st.markdown(f"""
                    <div class='recipe-card'>
                        <img src='{r['image']}' class='recipe-img'>
                        <div class='recipe-title'>{r['title']}</div>
                        <div class='recipe-meta'>⏱️ {r['readyInMinutes']} mins | 🍽️ Serves {r['servings']}</div>
                        <div class='recipe-meta'>Cuisine: {r['cuisines']}</div>
                        <a href='{r['sourceUrl']}' target='_blank'>🔗 View Full Recipe</a>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"❤️ Like {r['title']}", key=f"api_{r['title']}"):
                        if not any(x["title"] == r["title"] for x in st.session_state.user_taste["liked"]):
                            st.session_state.user_taste["liked"].append(r)
                            save_user_taste(st.session_state.user_taste)
                            st.success(f"Saved {r['title']} to liked recipes!")

        else:
            offline = st.session_state.search_results
            st.subheader("📁 Recipes from Offline Dataset")
            cols = st.columns(2)
            for i, (_, row) in enumerate(offline.iterrows()):
                img = f"https://source.unsplash.com/200x140/?food,{row['title'].replace(' ', '%20')}"
                g_link = google_search_link(row['title'])
                with cols[i % 2]:
                    st.markdown(f"""
                    <div class='recipe-card'>
                        <img src='{img}' class='recipe-img'>
                        <div class='recipe-title'>{row['title']}</div>
                        <div class='recipe-meta'>Ingredients: {', '.join(row['ingredients'][:6])}...</div>
                        <div class='recipe-meta'>Match Score: {round(row['Match Score'],2)}</div>
                        <a href='{g_link}' target='_blank'>🔗 Google Recipe Instructions</a>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"❤️ Like {row['title']}", key=f"off_{row['title']}"):
                        if not any(x["title"] == row["title"] for x in st.session_state.user_taste["liked"]):
                            enriched = enrich_offline_recipe(row["title"])
                            if enriched:
                                st.session_state.user_taste["liked"].append(enriched)
                            else:
                                st.session_state.user_taste["liked"].append({
                                    "title": row["title"],
                                    "ingredients": row["ingredients"],
                                    "readyInMinutes": "N/A",
                                    "servings": "N/A",
                                    "cuisines": "Not specified",
                                    "nutrition": "N/A",
                                    "image": img,
                                    "sourceUrl": g_link
                                })
                            save_user_taste(st.session_state.user_taste)
                            st.success(f"Saved {row['title']} to liked recipes!")

# -------------------- TAB 2 --------------------
with tab2:
    st.subheader("💾 Your Liked Recipes")
    liked = st.session_state.user_taste["liked"]

    if not liked:
        st.info("You haven’t liked any recipes yet.")
    else:
        cols = st.columns(2)
        for i, r in enumerate(liked):
            img = r.get("image", DEFAULT_IMAGE)
            ready = r.get("readyInMinutes", "N/A")
            serve = r.get("servings", "N/A")
            cuisine = r.get("cuisines", "Not specified")
            nutrition = r.get("nutrition", "N/A")
            source = r.get("sourceUrl", "#")

            with cols[i % 2]:
                st.markdown(f"""
                <div class='recipe-card'>
                    <img src='{img}' class='recipe-img'>
                    <div class='recipe-title'>{r['title']}</div>
                    <div class='recipe-meta'>⏱️ {ready} mins | 🍽️ Serves {serve}</div>
                    <div class='recipe-meta'>Cuisine: {cuisine}</div>
                    <div class='recipe-meta'>Nutrition: {nutrition}</div>
                    <a href='{source}' target='_blank'>🔗 View Full Recipe</a>
                </div>
                """, unsafe_allow_html=True)

                if st.button(f"💔 Remove {r['title']}", key=f"rem_{r['title']}"):
                    st.session_state.user_taste["liked"] = [
                        x for x in st.session_state.user_taste["liked"] if x["title"] != r["title"]
                    ]
                    save_user_taste(st.session_state.user_taste)
                    st.rerun()
