from math import sqrt
from typing import Dict, List, Tuple, Set, Optional
from flask import Flask, render_template, request, jsonify
import os
import re
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================
# Configuración de Flask
# ============================

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static"
)

# ============================
# Configuración OMDb (gratuito con API key)
# ============================
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
OMDB_URL = "https://www.omdbapi.com/"

# ============================
# Estructuras globales
# ============================

user_ratings: Dict[int, Dict[int, float]] = {}
item_ratings: Dict[int, Dict[int, float]] = {}
movie_genres: Dict[int, Set[str]] = {}
movie_titles: Dict[int, str] = {}
items_similares: Dict[int, List[Tuple[float, int]]] = {}
movie_posters: Dict[int, str] = {}  # cache de poster_url por movie_id

# ✅ NUEVO: timestamps del usuario
user_timestamps: Dict[int, Dict[int, int]] = {}  # user_id -> {movie_id: timestamp}

# ============================
# Utilidades para títulos y API
# ============================

def parse_title_and_year(raw_title: str) -> Tuple[str, Optional[int]]:
    raw_title = raw_title.strip()

    match = re.search(r"\((\d{4})\)\s*$", raw_title)
    year = int(match.group(1)) if match else None
    title = raw_title[:match.start()].strip() if match else raw_title

    # MovieLens: "Great Race, The" -> "The Great Race"
    comma_article = re.search(r"^(.*),\s*(The|A|An)$", title, re.IGNORECASE)
    if comma_article:
        title = f"{comma_article.group(2)} {comma_article.group(1)}"

    title = re.sub(r"\s+", " ", title).strip()
    return title, year


def fetch_poster_url(movie_id: int) -> Optional[str]:
    if movie_id in movie_posters:
        return movie_posters[movie_id]

    if not OMDB_API_KEY:
        return None

    title_raw = movie_titles.get(movie_id)
    if not title_raw:
        return None

    title, year = parse_title_and_year(title_raw)

    # 1) Intento exacto
    params = {"apikey": OMDB_API_KEY, "t": title, "type": "movie"}
    if year:
        params["y"] = str(year)

    try:
        r = requests.get(OMDB_URL, params=params, timeout=2)
        if r.status_code == 200:
            data = r.json()
            if data.get("Response") == "True":
                poster = data.get("Poster")
                if poster and poster != "N/A":
                    movie_posters[movie_id] = poster
                    return poster
    except Exception:
        pass

    # 2) Intento búsqueda (s=) y luego detalle por imdbID
    params = {"apikey": OMDB_API_KEY, "s": title, "type": "movie"}
    if year:
        params["y"] = str(year)

    try:
        r = requests.get(OMDB_URL, params=params, timeout=2)
        if r.status_code != 200:
            return None

        data = r.json()
        if data.get("Response") != "True":
            return None

        results = data.get("Search") or []
        if not results:
            return None

        imdb_id = results[0].get("imdbID")
        if not imdb_id:
            return None

        r2 = requests.get(OMDB_URL, params={"apikey": OMDB_API_KEY, "i": imdb_id}, timeout=2)
        if r2.status_code != 200:
            return None

        data2 = r2.json()
        if data2.get("Response") != "True":
            return None

        poster = data2.get("Poster")
        if poster and poster != "N/A":
            movie_posters[movie_id] = poster
            return poster

    except Exception:
        return None

    return None


def omdb_search_by_title(title: str, year: Optional[int] = None) -> Dict:
    if not OMDB_API_KEY:
        return {"Response": "False", "Error": "OMDB_API_KEY no configurada en el servidor."}

    params = {"apikey": OMDB_API_KEY, "t": title.strip(), "type": "movie"}
    if year:
        params["y"] = str(year)

    try:
        r = requests.get(OMDB_URL, params=params, timeout=4)
        if r.status_code != 200:
            return {"Response": "False", "Error": f"OMDb respondió con HTTP {r.status_code}"}
        return r.json()
    except Exception as e:
        return {"Response": "False", "Error": f"Error consultando OMDb: {str(e)}"}


@app.route("/search_movie", methods=["POST"])
def search_movie():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    year_raw = (data.get("year") or "").strip()

    if not title:
        return jsonify({"error": "Debes ingresar un título."}), 400

    year = None
    if year_raw:
        try:
            year = int(year_raw)
        except ValueError:
            return jsonify({"error": "El año debe ser un número (ej: 1995)."}), 400

    result = omdb_search_by_title(title, year)

    if result.get("Response") != "True":
        return jsonify({
            "ok": False,
            "title_query": title,
            "year_query": year,
            "error": result.get("Error", "No se encontró la película.")
        }), 200

    return jsonify({
        "ok": True,
        "query": {"title": title, "year": year},
        "movie": {
            "Title": result.get("Title"),
            "Year": result.get("Year"),
            "imdbID": result.get("imdbID"),
            "Genre": result.get("Genre"),
            "Poster": result.get("Poster"),
            "Plot": result.get("Plot"),
            "imdbRating": result.get("imdbRating"),
        }
    }), 200


# ============================
# Carga de datos MovieLens
# ============================

def load_movielens(
    path_data: str = "dataset/u.data",
    path_item: str = "dataset/u.item",
    path_genre: str = "dataset/u.genre",
) -> Tuple[
    Dict[int, Dict[int, float]],  # user_ratings
    Dict[int, Dict[int, float]],  # item_ratings
    Dict[int, Set[str]],          # movie_genres
    Dict[int, str],               # movie_titles
    Dict[int, Dict[int, int]],    # user_timestamps
]:
    # 1) Cargar géneros (índice -> nombre)
    genre_index_to_name: Dict[int, str] = {}
    with open(path_genre, encoding="latin-1") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 2:
                continue
            name, idx_str = parts[0], parts[1]
            if idx_str.isdigit():
                genre_index_to_name[int(idx_str)] = name

    # 2) Cargar info de películas
    movie_genres: Dict[int, Set[str]] = {}
    movie_titles: Dict[int, str] = {}

    with open(path_item, encoding="latin-1") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue

            movie_id = int(parts[0])
            title = parts[1]
            genre_flags = parts[5:]

            genres_for_movie: Set[str] = set()
            for idx, flag in enumerate(genre_flags):
                if flag == "1" and idx in genre_index_to_name:
                    genres_for_movie.add(genre_index_to_name[idx])

            movie_genres[movie_id] = genres_for_movie
            movie_titles[movie_id] = title

    # 3) Cargar ratings + timestamps
    user_ratings: Dict[int, Dict[int, float]] = {}
    item_ratings: Dict[int, Dict[int, float]] = {}
    user_timestamps: Dict[int, Dict[int, int]] = {}

    with open(path_data, encoding="latin-1") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue

            user_id = int(parts[0])
            movie_id = int(parts[1])
            rating = float(parts[2])
            ts = int(parts[3])

            user_ratings.setdefault(user_id, {})[movie_id] = rating
            item_ratings.setdefault(movie_id, {})[user_id] = rating
            user_timestamps.setdefault(user_id, {})[movie_id] = ts

    return user_ratings, item_ratings, movie_genres, movie_titles, user_timestamps


# ============================
# Métricas de similitud
# ============================

def euclidiana_item(item_ratings: Dict[int, Dict[int, float]], item1: int, item2: int) -> float:
    if item1 not in item_ratings or item2 not in item_ratings:
        return 0.0

    users1 = item_ratings[item1]
    users2 = item_ratings[item2]
    comunes = [u for u in users1 if u in users2]
    if not comunes:
        return 0.0

    sum_sq = 0.0
    for u in comunes:
        diff = users1[u] - users2[u]
        sum_sq += diff * diff

    dist = sqrt(sum_sq)
    return 1.0 / (1.0 + dist)


def jaccard_generos(movie1: int, movie2: int, movie_genres: Dict[int, Set[str]]) -> float:
    g1 = movie_genres.get(movie1, set())
    g2 = movie_genres.get(movie2, set())
    if not g1 or not g2:
        return 0.0

    inter = g1.intersection(g2)
    union = g1.union(g2)
    if not union:
        return 0.0
    return len(inter) / len(union)


def similitud_combinada_items(
    item_ratings: Dict[int, Dict[int, float]],
    movie_genres: Dict[int, Set[str]],
    item1: int,
    item2: int,
    alpha: float = 0.75
) -> float:
    sim_gen = jaccard_generos(item1, item2, movie_genres)
    if sim_gen == 0.0:
        return 0.0

    sim_rat = euclidiana_item(item_ratings, item1, item2)
    return alpha * sim_gen + (1.0 - alpha) * sim_rat


# ============================
# Cálculo de vecinos similares (item-based)
# ============================

def getSimilaresItems(
    item_ratings: Dict[int, Dict[int, float]],
    movie_genres: Dict[int, Set[str]],
    item_id: int,
    alpha: float = 0.75,
    n: int = 10
) -> List[Tuple[float, int]]:
    similitudes: List[Tuple[float, int]] = []

    for other_item in item_ratings:
        if other_item == item_id:
            continue
        sim = similitud_combinada_items(item_ratings, movie_genres, item_id, other_item, alpha)
        if sim > 0:
            similitudes.append((sim, other_item))

    similitudes.sort(reverse=True, key=lambda x: x[0])
    return similitudes[:n]


def calcularItemsSimilares(
    item_ratings: Dict[int, Dict[int, float]],
    movie_genres: Dict[int, Set[str]],
    alpha: float = 0.75,
    n: int = 10
) -> Dict[int, List[Tuple[float, int]]]:
    result: Dict[int, List[Tuple[float, int]]] = {}
    for item_id in item_ratings:
        result[item_id] = getSimilaresItems(item_ratings, movie_genres, item_id, alpha=alpha, n=n)
    return result


# ============================
# Recomendaciones para usuario (item-based)
# ============================

def getRecomendacionesItems(
    user_ratings: Dict[int, Dict[int, float]],
    items_similares: Dict[int, List[Tuple[float, int]]],
    usuario_id: int,
    movie_titles: Optional[Dict[int, str]] = None,
    movie_genres: Optional[Dict[int, Set[str]]] = None,
    top_n: int = 10
) -> List[Dict]:
    if usuario_id not in user_ratings:
        raise ValueError(f"Usuario {usuario_id} no encontrado en ratings.")

    notas_usuario = user_ratings[usuario_id]
    puntuaciones: Dict[int, float] = {}
    suma_similaridad: Dict[int, float] = {}

    for item, nota in notas_usuario.items():
        if item not in items_similares:
            continue

        for similaridad, item2 in items_similares[item]:
            if item2 in notas_usuario:
                continue

            puntuaciones.setdefault(item2, 0.0)
            puntuaciones[item2] += similaridad * nota

            suma_similaridad.setdefault(item2, 0.0)
            suma_similaridad[item2] += similaridad

    if not puntuaciones:
        return []

    rankings: List[Dict] = []
    for movie_id, total in puntuaciones.items():
        score = total / suma_similaridad[movie_id]
        title = movie_titles[movie_id] if movie_titles and movie_id in movie_titles else str(movie_id)
        genres_list = sorted(list(movie_genres.get(movie_id, []))) if movie_genres else []

        rankings.append({
            "score": round(score, 3),
            "movie_id": movie_id,
            "title": title,
            "genres": genres_list,
            "poster_url": None
        })

    rankings.sort(reverse=True, key=lambda x: x["score"])
    rankings = rankings[:top_n]

    for i in range(min(10, len(rankings))):
        rankings[i]["poster_url"] = fetch_poster_url(rankings[i]["movie_id"])

    return rankings


def getHistorialUsuario(
    user_ratings: Dict[int, Dict[int, float]],
    user_timestamps: Dict[int, Dict[int, int]],
    usuario_id: int,
    movie_titles: Dict[int, str],
    movie_genres: Dict[int, Set[str]],
    limit: int = 30,
    order: str = "recent",  # "recent" | "top"
) -> List[Dict]:
    if usuario_id not in user_ratings:
        raise ValueError(f"Usuario {usuario_id} no encontrado en ratings.")

    vistos: List[Dict] = []
    for movie_id, rating in user_ratings[usuario_id].items():
        ts = user_timestamps.get(usuario_id, {}).get(movie_id, 0)
        vistos.append({
            "movie_id": movie_id,
            "title": movie_titles.get(movie_id, str(movie_id)),
            "rating": float(rating),
            "genres": sorted(list(movie_genres.get(movie_id, set()))),
            "timestamp": ts,
            "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else None,
            "poster_url": None
        })

    if order == "top":
        vistos.sort(key=lambda x: (x["rating"], x["timestamp"]), reverse=True)
    else:
        vistos.sort(key=lambda x: x["timestamp"], reverse=True)

    vistos = vistos[:max(12, int(limit))]

    for i in range(min(12, len(vistos))):
        vistos[i]["poster_url"] = fetch_poster_url(vistos[i]["movie_id"])

    return vistos


# ============================
# Rutas Flask
# ============================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json() or {}
    user_id_raw = data.get("user_id")

    if user_id_raw is None or str(user_id_raw).strip() == "":
        return jsonify({"error": "Debes ingresar un ID de usuario."}), 400

    try:
        user_id = int(user_id_raw)
    except ValueError:
        return jsonify({"error": "El ID de usuario debe ser un número entero."}), 400

    try:
        recomendaciones = getRecomendacionesItems(
            user_ratings=user_ratings,
            items_similares=items_similares,
            usuario_id=user_id,
            movie_titles=movie_titles,
            movie_genres=movie_genres,
            top_n=10
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "Ocurrió un error al generar recomendaciones."}), 500

    return jsonify({"user_id": user_id, "recommendations": recomendaciones})


@app.route("/history", methods=["POST"])
def history():
    data = request.get_json() or {}
    user_id_raw = data.get("user_id")
    limit_raw = data.get("limit", 30)
    order = (data.get("order") or "recent").strip().lower()  # "recent" | "top"

    if user_id_raw is None or str(user_id_raw).strip() == "":
        return jsonify({"error": "Debes ingresar un ID de usuario."}), 400

    try:
        user_id = int(user_id_raw)
    except ValueError:
        return jsonify({"error": "El ID de usuario debe ser un número entero."}), 400

    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 30

    try:
        vistos = getHistorialUsuario(
            user_ratings=user_ratings,
            user_timestamps=user_timestamps,
            usuario_id=user_id,
            movie_titles=movie_titles,
            movie_genres=movie_genres,
            limit=limit,
            order=order
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"user_id": user_id, "seen": vistos})


# ============================
# Punto de entrada
# ============================

def init_app():
    global user_ratings, item_ratings, movie_genres, movie_titles, items_similares, user_timestamps

    print("Cargando datos MovieLens...")
    (user_ratings_local,
     item_ratings_local,
     movie_genres_local,
     movie_titles_local,
     user_timestamps_local) = load_movielens()

    print(f"Usuarios: {len(user_ratings_local)}, Películas: {len(item_ratings_local)}")

    print("Calculando matriz de items similares (priorizando género)...")
    alpha_genero = 0.8
    items_similares_local = calcularItemsSimilares(
        item_ratings=item_ratings_local,
        movie_genres=movie_genres_local,
        alpha=alpha_genero,
        n=10
    )
    print("Matriz de similitud calculada.")

    globals()["user_ratings"] = user_ratings_local
    globals()["item_ratings"] = item_ratings_local
    globals()["movie_genres"] = movie_genres_local
    globals()["movie_titles"] = movie_titles_local
    globals()["items_similares"] = items_similares_local
    globals()["user_timestamps"] = user_timestamps_local

    if not OMDB_API_KEY:
        print("⚠️  OMDB_API_KEY no está configurada. No se agregarán pósters.")
    else:
        print("OMDB_API_KEY detectada. Los pósters se irán obteniendo bajo demanda.")


if __name__ == "__main__":
    init_app()
    app.run(debug=True, use_reloader=False)
