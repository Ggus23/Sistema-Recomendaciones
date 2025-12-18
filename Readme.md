A continuación tienes un **README.md** bien detallado para tu `app.py`, describiendo **todas sus funciones**, endpoints, flujo de datos y configuración (basado en el código proporcionado ).

---

# 🎬 Sistema de Recomendación de Películas (Flask + MovieLens + OMDb)

Este proyecto es una aplicación web construida con **Flask** que implementa un **sistema de recomendación de películas (item-based)** usando el dataset **MovieLens (u.data / u.item / u.genre)**, y opcionalmente enriquece las recomendaciones con **pósters e información** desde la API de **OMDb**.

Incluye:

* Recomendación de películas para un usuario por **ID**.
* Historial de películas vistas por el usuario (ordenado por “reciente” o “top”).
* Búsqueda manual de película por título/año usando OMDb.
* Render de interfaz web desde `templates/index.html`.

---

## ✅ Requisitos

* Python 3.9+ recomendado
* Dependencias:

  * Flask
  * requests

---

## 📦 Instalación

1. Clonar / copiar el proyecto y entrar a la carpeta.

2. Crear y activar entorno virtual (opcional pero recomendado):

python -m venv .venv
source .venv/bin/activate

3. Instalar dependencias:

pip install flask requests

---

## 📁 Estructura esperada

La app asume esta estructura mínima:

```
/sistema-recomendaciones
  app.py
  /dataset
    u.data
    u.item
    u.genre
  /templates
    index.html
  /static
    main.js
    styles.css
```

> La configuración de Flask apunta a `templates/` y `static/` dentro del mismo directorio del `app.py`. 

---

## 🔑 Configuración de OMDb (Opcional)

Para que se carguen pósters y se habilite la búsqueda externa, necesitas una API Key de OMDb.

1. Crear variable de entorno:

```bash
export OMDB_API_KEY="TU_API_KEY"
```

2. Ejecutar la app normalmente.

📌 Si `OMDB_API_KEY` no está configurada:

* `/search_movie` devolverá error informativo.
* Las recomendaciones/historial retornarán `poster_url: null`.
* La app sigue funcionando con MovieLens, solo sin pósters. 

---

## ▶️ Ejecución

```bash
python app.py
```

El flujo de arranque hace:

1. `init_app()` carga MovieLens y precalcula similitudes.
2. `app.run(debug=True, use_reloader=False)` inicia el servidor. 

---

# 🧠 Descripción General del Sistema

La app trabaja con **recomendación basada en ítems**:

1. Carga los ratings del dataset:

* `user_ratings[user_id][movie_id] = rating`
* `item_ratings[movie_id][user_id] = rating`

2. Carga géneros y títulos de películas:

* `movie_genres[movie_id] = {"Action", "Comedy", ...}`
* `movie_titles[movie_id] = "Toy Story (1995)"`

3. Precalcula vecinos similares para cada película:

* `items_similares[movie_id] = [(sim, other_movie_id), ...]`

4. Para un usuario:

* toma las películas ya calificadas por el usuario,
* busca películas similares que el usuario **no vio**,
* calcula un score ponderado por similitud,
* devuelve el top de recomendaciones.

---

# 🌐 Endpoints (API)

## 1) `GET /`

Renderiza la página principal.

* **Respuesta:** HTML renderizado desde `templates/index.html`. 

---

## 2) `POST /recommend`

Genera recomendaciones para un usuario.

### Body (JSON)

```json
{
  "user_id": 10
}
```

### Validaciones

* `user_id` es obligatorio.
* `user_id` debe ser entero.
* Si el usuario no existe en `user_ratings`, devuelve error. 

### Respuesta (200)

```json
{
  "user_id": 10,
  "recommendations": [
    {
      "score": 4.321,
      "movie_id": 50,
      "title": "Star Wars (1977)",
      "genres": ["Action", "Adventure"],
      "poster_url": "https://..."
    }
  ]
}
```

### Errores comunes

* 400: ID vacío / no numérico / usuario no encontrado
* 500: error interno al recomendar 

---

## 3) `POST /history`

Devuelve el historial de películas vistas/calificadas por un usuario, con orden configurable.

### Body (JSON)

```json
{
  "user_id": 10,
  "limit": 30,
  "order": "recent"
}
```

### Parámetros

* `user_id` (obligatorio): entero.
* `limit` (opcional): por defecto 30.
* `order` (opcional):

  * `"recent"`: ordena por timestamp descendente (más reciente primero)
  * `"top"`: ordena por rating desc, y luego timestamp desc

> Nota: internamente se fuerza un mínimo efectivo de resultados para posters/historial (usa `max(12, limit)` y carga hasta 12 pósters). 

### Respuesta (200)

```json
{
  "user_id": 10,
  "seen": [
    {
      "movie_id": 1,
      "title": "Toy Story (1995)",
      "rating": 5.0,
      "genres": ["Animation", "Children's", "Comedy"],
      "timestamp": 874965758,
      "date": "1997-09-18",
      "poster_url": "https://..."
    }
  ]
}
```

---

## 4) `POST /search_movie`

Busca una película en OMDb por título (y opcionalmente año) y devuelve metadata.

### Body (JSON)

```json
{
  "title": "Toy Story",
  "year": "1995"
}
```

### Validaciones

* `title` obligatorio.
* `year` si se envía debe ser número. 

### Respuesta (200) OK

```json
{
  "ok": true,
  "query": {"title":"Toy Story","year":1995},
  "movie": {
    "Title": "Toy Story",
    "Year": "1995",
    "imdbID": "tt0114709",
    "Genre": "Animation, Adventure, Comedy",
    "Poster": "https://...",
    "Plot": "...",
    "imdbRating": "8.3"
  }
}
```

### Respuesta (200) no encontrada / error OMDb

```json
{
  "ok": false,
  "title_query": "xxxx",
  "year_query": null,
  "error": "No se encontró la película."
}
```

### Error si falta OMDB_API_KEY

```json
{
  "ok": false,
  "error": "OMDB_API_KEY no configurada en el servidor."
}
```

---

# 🧩 Funciones del Código (Detalladas)

A continuación se describe cada función y su propósito.

---

## Utilidades de títulos y OMDb

### `parse_title_and_year(raw_title) -> (title, year)`

* Limpia un título crudo de MovieLens.
* Extrae año final si viene como `"(1995)"`.
* Convierte formato MovieLens con artículo al final:

  * `"Great Race, The"` → `"The Great Race"`
* Normaliza espacios. 

---

### `fetch_poster_url(movie_id) -> Optional[str]`

Obtiene el póster de una película usando OMDb con estrategia de 2 pasos:

1. **Cache local**: si ya está en `movie_posters`, lo retorna.
2. Si no hay `OMDB_API_KEY` → retorna `None`.
3. Obtiene `title_raw` desde `movie_titles[movie_id]`:

   * parsea `title` y `year` con `parse_title_and_year`.
4. **Intento exacto** con `t=title` (y `y=year` si existe).
5. Si falla, hace **búsqueda** con `s=title` (y año si existe),
   toma el primer `imdbID`, y consulta detalles con `i=imdbID`.
6. Si encuentra `Poster` válido, lo guarda en cache.

Tiempo de espera:

* requests timeout 2s en varias llamadas.

> Si ocurre excepción, falla silenciosamente y devuelve `None`. 

---

### `omdb_search_by_title(title, year=None) -> Dict`

Consulta OMDb con `t=title` y devuelve el JSON.

* Si falta API Key retorna:

  * `{"Response":"False","Error":"OMDB_API_KEY no configurada..."}`

* Maneja errores HTTP y excepciones. 

---

## Carga de datos MovieLens

### `load_movielens(path_data, path_item, path_genre) -> (user_ratings, item_ratings, movie_genres, movie_titles, user_timestamps)`

Carga y construye las estructuras base del sistema:

1. `u.genre`: mapa índice → nombre de género.
2. `u.item`: por película:

   * id
   * título
   * flags de géneros (a partir del campo 6 en adelante)
3. `u.data`: por rating:

   * user_id, movie_id, rating, timestamp

Devuelve:

* `user_ratings[user_id][movie_id] = rating`
* `item_ratings[movie_id][user_id] = rating`
* `movie_genres[movie_id] = set(genres)`
* `movie_titles[movie_id] = title`
* `user_timestamps[user_id][movie_id] = timestamp` 

---

## Métricas de similitud

### `euclidiana_item(item_ratings, item1, item2) -> float`

Calcula similitud basada en distancia euclidiana entre dos películas según usuarios en común:

* Busca usuarios que calificaron ambas.
* Suma cuadrados de diferencias.
* Distancia = `sqrt(sum_sq)`
* Similitud = `1 / (1 + distancia)`

Si no hay usuarios comunes o faltan items → 0.0 

---

### `jaccard_generos(movie1, movie2, movie_genres) -> float`

Similitud de géneros por **Jaccard**:

* `|intersección| / |unión|`
* Si alguna película no tiene géneros → 0.0 

---

### `similitud_combinada_items(item_ratings, movie_genres, item1, item2, alpha=0.75) -> float`

Combina:

* similitud de géneros (Jaccard)
* similitud por ratings (Euclidiana)

Fórmula:

* `alpha * sim_gen + (1 - alpha) * sim_rat`

**Regla importante:** si `sim_gen == 0`, retorna 0 directamente.
Esto fuerza que solo se consideren similares si comparten géneros. 

---

## Vecinos similares (Item-based)

### `getSimilaresItems(item_ratings, movie_genres, item_id, alpha=0.75, n=10) -> List[(sim, other_item)]`

Para una película `item_id`:

* recorre todas las demás películas
* calcula similitud combinada
* filtra sim > 0
* ordena desc
* devuelve top `n` 

---

### `calcularItemsSimilares(item_ratings, movie_genres, alpha=0.75, n=10) -> Dict[item_id] = vecinos`

Genera la matriz completa:

* para cada `item_id` calcula su top N vecinos similares
* devuelve un diccionario con listas de tuplas (similitud, movie_id) 

---

## Recomendaciones e historial

### `getRecomendacionesItems(user_ratings, items_similares, usuario_id, movie_titles=None, movie_genres=None, top_n=10) -> List[Dict]`

Genera recomendaciones para un usuario:

1. Obtiene películas calificadas por el usuario.
2. Para cada película vista:

   * revisa sus vecinos en `items_similares`
   * ignora películas que el usuario ya vio
   * acumula:

     * `puntuaciones[item2] += similaridad * nota_usuario`
     * `suma_similaridad[item2] += similaridad`
3. Calcula score final:

   * `score = total / suma_similaridad[movie_id]`
4. Agrega metadata:

   * title desde `movie_titles`
   * genres desde `movie_genres`
5. Ordena por score desc y corta a `top_n`
6. Enriquecimiento:

   * para las primeras 10 recomienda obtener `poster_url` vía OMDb.

Si usuario no existe: `ValueError`. 

---

### `getHistorialUsuario(user_ratings, user_timestamps, usuario_id, movie_titles, movie_genres, limit=30, order="recent")`

Construye historial de películas vistas:

Para cada película calificada por el usuario:

* obtiene `rating`, `timestamp`
* genera `date` en UTC con `datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")`
* agrega géneros y título
* `poster_url` inicialmente `None`

Orden:

* `"recent"`: por timestamp desc
* `"top"`: por rating desc y luego timestamp desc

Luego:

* recorta a `max(12, limit)`
* carga pósters para las primeras 12

Si usuario no existe: `ValueError`. 

---

# ⚙️ Inicialización del sistema

### `init_app()`

Se ejecuta al correr el script principal.

Hace:

1. Carga MovieLens con `load_movielens()`.
2. Imprime cantidad de usuarios/películas.
3. Calcula similitudes:

   * `alpha_genero = 0.8` (prioriza más géneros)
   * `n=10` vecinos por película
4. Guarda resultados en variables globales con `globals()[...]`.
5. Informa si OMDb está disponible o no. 

---

# 🧪 Ejemplos de uso (cURL)

## Recomendaciones

```bash
curl -X POST http://127.0.0.1:5000/recommend \
  -H "Content-Type: application/json" \
  -d '{"user_id": 10}'
```

## Historial

```bash
curl -X POST http://127.0.0.1:5000/history \
  -H "Content-Type: application/json" \
  -d '{"user_id": 10, "limit": 20, "order": "top"}'
```

## Buscar en OMDb

```bash
curl -X POST http://127.0.0.1:5000/search_movie \
  -H "Content-Type: application/json" \
  -d '{"title":"Toy Story", "year":"1995"}'
```

---

# 🛠️ Troubleshooting

## “OMDB_API_KEY no configurada…”

Solución: exporta la variable de entorno y reinicia el servidor.

```bash
export OMDB_API_KEY="TU_API_KEY"
python app.py
```

## Pósters salen como null

* Si no hay OMDb key: esperado.
* Si hay key: OMDb se consulta “bajo demanda”; algunas películas pueden no encontrarse por diferencias de título/año. 

---

# 📌 Notas técnicas importantes

* La app usa **estructuras globales** precargadas (rápido para demo, pero no ideal para producción con múltiples workers).
* Los requests a OMDb tienen timeout y manejan excepciones para no tumbar la app.
* La similitud combinada **exige coincidencia de géneros** para considerar un ítem similar (si Jaccard=0, similitud=0). 

---
