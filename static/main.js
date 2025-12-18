(() => {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function assertEl(el, name) {
    if (!el) throw new Error(`No se encontró el elemento "${name}". Revisa el id en index.html.`);
    return el;
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function safeJson(response) {
    try {
      return await response.json();
    } catch {
      const raw = await response.text();
      throw new Error("Respuesta no-JSON: " + raw.slice(0, 200));
    }
  }

  function clamp(n, min, max) {
    const x = Number(n);
    if (Number.isNaN(x)) return min;
    return Math.max(min, Math.min(max, x));
  }

  document.addEventListener("DOMContentLoaded", () => {
    // ==========
    // ELEMENTOS
    // ==========
    let form, userIdInput, statusDiv, resultsContainer, submitBtn, btnText, btnSpinner, chips;
    let movieSearchForm, movieTitleInput, movieYearInput, omdbContainer, searchBtn, searchText, searchSpinner;
    let historyContainer;

    try {
      form = assertEl($("recommendation-form"), "recommendation-form");
      userIdInput = assertEl($("user-id"), "user-id");
      statusDiv = assertEl($("status"), "status");
      resultsContainer = assertEl($("results-container"), "results-container");
      submitBtn = assertEl($("submit-btn"), "submit-btn");
      btnText = assertEl($("button-text"), "button-text");
      btnSpinner = assertEl($("button-spinner"), "button-spinner");
      chips = document.querySelectorAll(".chip");

      movieSearchForm = assertEl($("movie-search-form"), "movie-search-form");
      movieTitleInput = assertEl($("movie-title"), "movie-title");
      movieYearInput = assertEl($("movie-year"), "movie-year");
      omdbContainer = assertEl($("omdb-container"), "omdb-container");
      searchBtn = assertEl($("search-btn"), "search-btn");
      searchText = assertEl($("search-text"), "search-text");
      searchSpinner = assertEl($("search-spinner"), "search-spinner");

      historyContainer = assertEl($("history-container"), "history-container");
    } catch (e) {
      console.error(e);
      // Si falla el DOM, al menos lo mostramos en consola.
      return;
    }

    // ==========
    // UI HELPERS
    // ==========
    function setSearchLoading(isLoading) {
      if (isLoading) {
        searchBtn.disabled = true;
        searchText.textContent = "Buscando...";
        searchSpinner.style.display = "block";
      } else {
        searchBtn.disabled = false;
        searchText.textContent = "Buscar en OMDb";
        searchSpinner.style.display = "none";
      }
    }

    function setLoading(isLoading) {
      if (isLoading) {
        submitBtn.disabled = true;
        btnText.textContent = "Calculando...";
        btnSpinner.style.display = "block";
      } else {
        submitBtn.disabled = false;
        btnText.textContent = "Obtener recomendaciones";
        btnSpinner.style.display = "none";
      }
    }

    function setStatus(message, type = "muted") {
      statusDiv.textContent = message;
      statusDiv.classList.remove("error", "ok", "status-muted");
      if (type === "error") statusDiv.classList.add("error");
      else if (type === "ok") statusDiv.classList.add("ok");
      else statusDiv.classList.add("status-muted");
    }

    // ==========
    // RENDER
    // ==========
    function renderOmdbResult(payload) {
      if (!payload || !payload.ok) {
        const msg = payload?.error || "No se encontró la película.";
        omdbContainer.innerHTML = `
          <div class="empty-state">
            <strong>OMDb:</strong> ${escapeHtml(msg)}
          </div>
        `;
        return;
      }

      const m = payload.movie || {};
      const poster = (m.Poster && m.Poster !== "N/A")
        ? `<img src="${escapeHtml(m.Poster)}" alt="Poster ${escapeHtml(m.Title)}" style="width:110px;height:165px;object-fit:cover;border-radius:10px;border:1px solid rgba(148,163,184,0.18);">`
        : `<div style="width:110px;height:165px;border-radius:10px;border:1px dashed rgba(148,163,184,0.25);display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:0.8rem;">Sin imagen</div>`;

      omdbContainer.innerHTML = `
        <div class="card" style="padding: 14px; margin-top: 10px;">
          <div style="display:flex; gap:12px; position:relative; z-index:1;">
            ${poster}
            <div style="min-width:0;">
              <div style="font-weight:600; font-size:1rem;">${escapeHtml(m.Title)} (${escapeHtml(m.Year)})</div>
              <div style="color:var(--text-muted); font-size:0.82rem; margin-top:2px;">
                IMDb: ${escapeHtml(m.imdbID || "-")} · Rating: ${escapeHtml(m.imdbRating || "-")}
              </div>
              <div style="margin-top:6px; font-size:0.82rem;">
                <strong>Géneros:</strong> ${escapeHtml(m.Genre || "-")}
              </div>
              <div style="margin-top:6px; font-size:0.82rem; color:var(--text-muted);">
                ${escapeHtml(m.Plot || "")}
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function renderResults(data) {
      const recommendations = data?.recommendations || [];

      if (!recommendations.length) {
        resultsContainer.innerHTML = `
          <div class="empty-state">
            <strong>No se encontraron recomendaciones para este usuario.</strong><br/>
            Es posible que el usuario tenga muy pocas películas calificadas.
          </div>
        `;
        return;
      }

      let cards = "";
      recommendations.forEach((rec, index) => {
        const rawScore = Number(rec?.score);
        const clampedScore = clamp(rawScore, 0, 5);
        const scoreText = `${clampedScore.toFixed(1)} / 5`;

        const genres = (rec?.genres || [])
          .map(g => `<span class="genre-chip">${escapeHtml(g)}</span>`)
          .join(" ");

        const posterUrl = rec?.poster_url;
        const posterBlock = posterUrl
          ? `<img src="${escapeHtml(posterUrl)}" alt="Póster de ${escapeHtml(rec?.title)}" class="movie-poster-img" loading="lazy" />`
          : `<div class="movie-poster-fallback">Sin<br>imagen</div>`;

        cards += `
          <article class="movie-card">
            <div class="movie-poster-wrapper">
              ${posterBlock}
            </div>
            <div class="movie-info">
              <div class="movie-info-top">
                <div class="movie-title-main">${escapeHtml(rec?.title)}</div>
                <div class="movie-title-sub">ID: ${escapeHtml(rec?.movie_id)}</div>
                <div class="movie-genres">
                  <div class="pill-genres">${genres}</div>
                </div>
              </div>
              <div class="movie-meta-row">
                <span class="score-pill-small">${escapeHtml(scoreText)}</span>
                <span class="movie-rank">#${index + 1} en el ranking</span>
              </div>
            </div>
          </article>
        `;
      });

      resultsContainer.innerHTML = `<div class="results-grid">${cards}</div>`;
    }

    function renderHistory(payload) {
      const seen = payload?.seen || [];

      if (!seen.length) {
        historyContainer.innerHTML = `
          <div class="empty-state">
            <strong>Historial vacío.</strong> No se encontraron películas calificadas para este usuario.
          </div>
        `;
        return;
      }

      let cards = "";
      seen.forEach((m) => {
        const genres = (m?.genres || [])
          .map(g => `<span class="genre-chip">${escapeHtml(g)}</span>`)
          .join(" ");

        const dateLine = m?.date
          ? `<div class="movie-title-sub">Fecha: ${escapeHtml(m.date)}</div>`
          : "";

        const posterUrl = m?.poster_url;
        const posterBlock = posterUrl
          ? `<img src="${escapeHtml(posterUrl)}" alt="Póster de ${escapeHtml(m?.title)}" class="movie-poster-img" loading="lazy" />`
          : `<div class="movie-poster-fallback">Visto</div>`;

        cards += `
          <article class="movie-card" style="opacity:0.95;">
            <div class="movie-poster-wrapper">
              ${posterBlock}
            </div>
            <div class="movie-info">
              <div class="movie-info-top">
                <div class="movie-title-main">${escapeHtml(m?.title)}</div>
                <div class="movie-title-sub">ID: ${escapeHtml(m?.movie_id)}</div>
                ${dateLine}
                <div class="movie-genres">
                  <div class="pill-genres">${genres}</div>
                </div>
              </div>
              <div class="movie-meta-row">
                <span class="score-pill-small">${Number(m?.rating ?? 0).toFixed(1)} / 5</span>
                <span class="movie-rank">Calificación del usuario</span>
              </div>
            </div>
          </article>
        `;
      });

      historyContainer.innerHTML = `
        <div class="card-secondary-header" style="margin-top:12px;">
          <h2 class="card-secondary-title">Películas que ya vio el usuario (historial reciente)</h2>
          <span class="pill-accent">Historial</span>
        </div>
        <div class="results-grid">${cards}</div>
      `;
    }

    // ==========
    // EVENTOS
    // ==========
    movieSearchForm.addEventListener("submit", async (event) => {
      event.preventDefault();

      const title = movieTitleInput.value.trim();
      const year = movieYearInput.value.trim();

      if (!title) {
        omdbContainer.innerHTML = `
          <div class="empty-state">
            <strong>Error:</strong> Ingresa un título para buscar.
          </div>
        `;
        return;
      }

      setSearchLoading(true);

      try {
        const resp = await fetch("/search_movie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, year })
        });

        const data = await safeJson(resp);
        renderOmdbResult(data);
      } catch (e) {
        omdbContainer.innerHTML = `
          <div class="empty-state">
            <strong>Error:</strong> ${escapeHtml(e?.message || "No se pudo conectar con Flask para buscar en OMDb.")}
          </div>
        `;
      } finally {
        setSearchLoading(false);
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const userId = userIdInput.value.trim();
      if (!userId) {
        setStatus("Por favor ingresa un ID de usuario.", "error");
        return;
      }

      setLoading(true);
      setStatus("Consultando recomendaciones...", "muted");

      try {
        // RECOMMEND
        const response = await fetch("/recommend", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId })
        });

        const data = await safeJson(response);

        if (!response.ok) {
          const message = data?.error || "Error desconocido en la API.";
          setStatus(message, "error");
          resultsContainer.innerHTML = `
            <div class="empty-state">
              <strong>Error:</strong> ${escapeHtml(message)}
            </div>
          `;
        } else {
          setStatus(`Mostrando recomendaciones para el usuario ${data.user_id}.`, "ok");
          renderResults(data);
        }

        // HISTORY
        try {
          const histResp = await fetch("/history", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: userId, limit: 12, order: "recent" })
          });

          const histData = await safeJson(histResp);
          if (histResp.ok) renderHistory(histData);
        } catch (e) {
          historyContainer.innerHTML = `
            <div class="empty-state">
              <strong>Historial:</strong> ${escapeHtml(e?.message || "No se pudo cargar el historial.")}
            </div>
          `;
        }

      } catch (err) {
        setStatus("Error de conexión o respuesta inválida: " + (err?.message || ""), "error");
        resultsContainer.innerHTML = `
          <div class="empty-state">
            <strong>Error.</strong><br/>
            ${escapeHtml(err?.message || "Asegúrate de que el servidor Flask está en ejecución.")}
          </div>
        `;
      } finally {
        setLoading(false);
      }
    });

    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        const id = chip.getAttribute("data-user-id");
        if (!id) return;
        userIdInput.value = id;
        userIdInput.focus();
      });
    });

    // Estado inicial
    setStatus("Esperando un ID de usuario...", "muted");
  });
})();
