(function () {
  "use strict";

  const app = document.getElementById("series-app");
  const API_FOLDERS = app.dataset.apiFolders;
  const API_FILES = app.dataset.apiFiles;
  const API_RENAME = app.dataset.apiRename;
  const API_SUGGEST_TITLE = app.dataset.apiSuggestTitle;
  const API_SUBTITLE_SEARCH = app.dataset.apiSubtitleSearch;
  const API_SUBTITLE_DOWNLOAD = app.dataset.apiSubtitleDownload;
  const INITIAL_PATH = app.dataset.initialPath;

  const treeEl = document.getElementById("series-tree");
  const selectedPathInput = document.getElementById("series-selected-path");
  const videoListDiv = document.getElementById("series-video-list");
  const subtitleListDiv = document.getElementById("series-subtitle-list");
  const noFilesMsg = document.getElementById("series-no-files");
  const statusDiv = document.getElementById("series-status");
  const refreshBtn = document.getElementById("series-refresh");
  const renameSubsBtn = document.getElementById("series-rename-subs");
  const renameVideosBtn = document.getElementById("series-rename-videos");

  const suggestedTitleInput = document.getElementById("series-suggested-title");
  const keywordInput = document.getElementById("series-keyword");
  const freeQueryInput = document.getElementById("series-free-query");
  const searchBtn = document.getElementById("series-search-btn");
  const searchStatusDiv = document.getElementById("series-search-status");
  const searchResultsDiv = document.getElementById("series-search-results");

  function csrfToken() {
    const input = app.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function joinPath(base, name) {
    if (!base) return name;
    return base.endsWith("/") ? `${base}${name}` : `${base}/${name}`;
  }

  function showStatus(message, isError) {
    statusDiv.textContent = message;
    statusDiv.classList.remove("hidden", "ok", "error");
    statusDiv.classList.add(isError ? "error" : "ok");
  }

  function clearStatus() {
    statusDiv.classList.add("hidden");
  }

  function showSearchStatus(message, isError) {
    searchStatusDiv.textContent = message;
    searchStatusDiv.classList.remove("hidden", "ok", "error");
    searchStatusDiv.classList.add(isError ? "error" : "ok");
  }

  function clearSearchStatus() {
    searchStatusDiv.classList.add("hidden");
  }

  // ── Listado de videos/subtítulos con drag & drop ──────────────────────────

  function updateIndices(listEl) {
    Array.from(listEl.children).forEach((li, i) => {
      const idxEl = li.querySelector(".series-file-index");
      if (idxEl) idxEl.textContent = `${i + 1}.`;
    });
  }

  function buildFileList(container, files, listId) {
    container.innerHTML = "";
    if (files.length === 0) {
      const empty = document.createElement("p");
      empty.className = "series-muted";
      empty.textContent = "Sin archivos.";
      container.appendChild(empty);
      return;
    }

    const ul = document.createElement("ul");
    ul.id = listId;
    ul.style.listStyle = "none";
    ul.style.padding = "0";
    ul.style.margin = "0";

    files.forEach((file, i) => {
      const li = document.createElement("li");
      li.className = "series-file-item";
      li.innerHTML = `
        <span class="series-drag-handle"><i class="bi bi-grip-vertical"></i></span>
        <span class="series-file-index">${i + 1}.</span>
        <span class="series-file-name">${file}</span>
      `;
      ul.appendChild(li);
    });

    container.appendChild(ul);
    // eslint-disable-next-line no-undef
    new Sortable(ul, {
      animation: 150,
      ghostClass: "series-sortable-ghost",
      handle: ".series-drag-handle",
      onUpdate: () => updateIndices(ul),
    });
  }

  function displayFiles(data) {
    clearStatus();
    noFilesMsg.classList.add("hidden");

    const videoFiles = data.video_files || [];
    const subFiles = data.sub_files || [];

    buildFileList(videoListDiv, videoFiles, "series-video-sortable");
    buildFileList(subtitleListDiv, subFiles, "series-subtitle-sortable");

    if (videoFiles.length === 0 && subFiles.length === 0) {
      noFilesMsg.classList.remove("hidden");
    } else if (videoFiles.length !== subFiles.length) {
      showStatus("La cantidad de videos y subtítulos no coincide — el renombrado podría fallar.", true);
    }
  }

  async function fetchAndDisplayFiles(path) {
    clearStatus();
    videoListDiv.innerHTML = '<p class="series-muted">Cargando…</p>';
    subtitleListDiv.innerHTML = '<p class="series-muted">Cargando…</p>';
    noFilesMsg.classList.add("hidden");

    try {
      const resp = await fetch(`${API_FILES}?path=${encodeURIComponent(path)}`);
      if (!resp.ok) throw new Error("Respuesta no exitosa del servidor.");
      const data = await resp.json();
      displayFiles(data);
    } catch (err) {
      console.error("Error al listar archivos:", err);
      videoListDiv.innerHTML = '<p class="series-error">Error al cargar archivos.</p>';
      subtitleListDiv.innerHTML = "";
      showStatus("Error al cargar los archivos. Revisá la consola del navegador.", true);
    }
  }

  // ── Búsqueda y descarga de subtítulos ─────────────────────────────────────

  async function fetchSuggestedTitle(path) {
    suggestedTitleInput.value = "Cargando…";
    searchResultsDiv.innerHTML = "";
    clearSearchStatus();
    try {
      const resp = await fetch(`${API_SUGGEST_TITLE}?path=${encodeURIComponent(path)}`);
      if (!resp.ok) throw new Error("Respuesta no exitosa del servidor.");
      const data = await resp.json();
      suggestedTitleInput.value = data.title || "";
    } catch (err) {
      console.error("Error al sugerir título:", err);
      suggestedTitleInput.value = "";
      showSearchStatus("No se pudo sugerir un título. Escribilo manualmente.", true);
    }
  }

  function renderSearchResults(results, path) {
    searchResultsDiv.innerHTML = "";

    if (!results || results.length === 0) {
      const empty = document.createElement("p");
      empty.className = "series-muted";
      empty.textContent = "Sin resultados.";
      searchResultsDiv.appendChild(empty);
      return;
    }

    results.forEach((item) => {
      const subtitleId = item.id !== undefined ? item.id : item.subtitle_id;

      const card = document.createElement("div");
      card.className = "series-sub-result";

      const header = document.createElement("div");
      header.className = "series-sub-result-header";

      const title = document.createElement("span");
      title.className = "series-sub-title";
      title.textContent = item.title || "(sin título)";

      const downloads = document.createElement("span");
      downloads.className = "series-sub-downloads";
      downloads.innerHTML = `<i class="bi bi-download"></i> ${item.downloads != null ? item.downloads : "?"}`;

      header.appendChild(title);
      header.appendChild(downloads);

      const uploader = document.createElement("div");
      uploader.className = "series-sub-uploader";
      uploader.textContent = `por ${item.uploader_name || "desconocido"}`;

      const desc = document.createElement("div");
      desc.className = "series-sub-desc";
      desc.textContent = item.description || "";

      const downloadBtn = document.createElement("button");
      downloadBtn.type = "button";
      downloadBtn.className = "btn-accent series-sub-download-btn";
      downloadBtn.textContent = "Descargar";
      downloadBtn.addEventListener("click", () => downloadSubtitle(subtitleId, path, downloadBtn));

      card.appendChild(header);
      card.appendChild(uploader);
      if (item.description) card.appendChild(desc);
      card.appendChild(downloadBtn);

      searchResultsDiv.appendChild(card);
    });
  }

  async function performSearch() {
    const path = selectedPathInput.value;
    if (!path) {
      showSearchStatus("Seleccioná una carpeta primero.", true);
      return;
    }

    const title = suggestedTitleInput.value.trim();
    const keyword = keywordInput.value.trim();
    const freeQuery = freeQueryInput.value.trim();

    if (!title && !freeQuery) {
      showSearchStatus("Ingresá un título o una búsqueda libre.", true);
      return;
    }

    clearSearchStatus();
    searchResultsDiv.innerHTML = '<p class="series-muted">Buscando…</p>';
    searchBtn.disabled = true;

    const params = new URLSearchParams({ title, keyword, free_query: freeQuery });

    try {
      const resp = await fetch(`${API_SUBTITLE_SEARCH}?${params.toString()}`);
      if (!resp.ok) throw new Error("Respuesta no exitosa del servidor.");
      const data = await resp.json();
      renderSearchResults(data.results || data, path);
    } catch (err) {
      console.error("Error en la búsqueda de subtítulos:", err);
      searchResultsDiv.innerHTML = "";
      showSearchStatus("Error al buscar subtítulos. Revisá la consola del navegador.", true);
    } finally {
      searchBtn.disabled = false;
    }
  }

  async function downloadSubtitle(subtitleId, path, btn) {
    if (!subtitleId) {
      showSearchStatus("No se pudo identificar el subtítulo elegido.", true);
      return;
    }

    btn.disabled = true;
    btn.textContent = "Descargando…";
    clearSearchStatus();

    try {
      const resp = await fetch(API_SUBTITLE_DOWNLOAD, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ subtitle_id: subtitleId, path }),
      });
      const result = await resp.json();
      showSearchStatus(result.message || (resp.ok ? "Subtítulos descargados y extraídos." : "Error al descargar."), !resp.ok);
      if (resp.ok) fetchAndDisplayFiles(path);
    } catch (err) {
      console.error("Error al descargar subtítulo:", err);
      showSearchStatus("Ocurrió un error inesperado. Revisá la consola del navegador.", true);
    } finally {
      btn.disabled = false;
      btn.textContent = "Descargar";
    }
  }

  searchBtn.addEventListener("click", performSearch);

  // ── Árbol de carpetas ──────────────────────────────────────────────────────

  function createFolderNode(name, parentPath) {
    const fullPath = joinPath(parentPath, name);

    const li = document.createElement("li");

    const row = document.createElement("div");
    row.className = "series-folder-row";

    const toggle = document.createElement("span");
    toggle.className = "series-folder-toggle";
    toggle.innerHTML = '<i class="bi bi-chevron-right"></i>';

    const label = document.createElement("span");
    label.innerHTML = `<i class="bi bi-folder-fill" style="color:var(--accent-dim);"></i> ${name}`;
    label.style.flexGrow = "1";

    row.appendChild(toggle);
    row.appendChild(label);
    li.appendChild(row);

    const subList = document.createElement("ul");
    subList.classList.add("hidden");
    li.appendChild(subList);

    row.addEventListener("click", (evt) => {
      if (evt.target.closest(".series-folder-toggle")) return;
      document.querySelectorAll(".series-folder-row.selected").forEach((el) => el.classList.remove("selected"));
      row.classList.add("selected");
      selectedPathInput.value = fullPath;
      fetchAndDisplayFiles(fullPath);
      fetchSuggestedTitle(fullPath);
    });

    toggle.addEventListener("click", async () => {
      const expanded = toggle.classList.toggle("expanded");
      subList.classList.toggle("hidden", !expanded);
      toggle.innerHTML = expanded
        ? '<i class="bi bi-chevron-down"></i>'
        : '<i class="bi bi-chevron-right"></i>';

      if (expanded && subList.children.length === 0) {
        try {
          const resp = await fetch(`${API_FOLDERS}?path=${encodeURIComponent(fullPath)}`);
          if (!resp.ok) throw new Error("No se pudo cargar la carpeta.");
          const subfolders = await resp.json();
          if (subfolders.length === 0) {
            const emptyLi = document.createElement("li");
            emptyLi.className = "series-muted";
            emptyLi.textContent = "Carpeta vacía.";
            subList.appendChild(emptyLi);
          } else {
            subfolders.forEach((sub) => subList.appendChild(createFolderNode(sub, fullPath)));
          }
        } catch (err) {
          console.error("Error al listar subcarpetas:", err);
          const errorLi = document.createElement("li");
          errorLi.className = "series-error";
          errorLi.textContent = "Error al cargar.";
          subList.appendChild(errorLi);
        }
      }
    });

    return li;
  }

  async function loadInitialTree() {
    selectedPathInput.value = INITIAL_PATH;
    try {
      const resp = await fetch(`${API_FOLDERS}?path=${encodeURIComponent(INITIAL_PATH)}`);
      if (!resp.ok) throw new Error("Respuesta no exitosa del servidor.");
      const subfolders = await resp.json();

      treeEl.innerHTML = "";
      if (subfolders.length === 0) {
        treeEl.innerHTML = '<li class="series-muted">Carpeta raíz vacía.</li>';
      } else {
        subfolders.forEach((sub) => treeEl.appendChild(createFolderNode(sub, INITIAL_PATH)));
      }
      fetchAndDisplayFiles(INITIAL_PATH);
      fetchSuggestedTitle(INITIAL_PATH);
    } catch (err) {
      console.error("Error al cargar el árbol inicial:", err);
      treeEl.innerHTML = '<li class="series-error">Error al cargar SERIES_ROOT. Revisá la configuración del servidor.</li>';
    }
  }

  // ── Tabs ────────────────────────────────────────────────────────────────────

  document.querySelectorAll(".series-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".series-tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".series-tab-content").forEach((c) => c.classList.add("hidden"));
      btn.classList.add("active");
      document.getElementById(`series-tab-${btn.dataset.tab}`).classList.remove("hidden");
    });
  });

  // ── Renombrado ───────────────────────────────────────────────────────────────

  async function handleRename(action) {
    const videoList = document.getElementById("series-video-sortable");
    const subtitleList = document.getElementById("series-subtitle-sortable");
    clearStatus();

    const videoFiles = videoList
      ? Array.from(videoList.children).map((li) => li.querySelector(".series-file-name").textContent)
      : [];
    const subFiles = subtitleList
      ? Array.from(subtitleList.children).map((li) => li.querySelector(".series-file-name").textContent)
      : [];
    const path = selectedPathInput.value;

    if (videoFiles.length !== subFiles.length) {
      showStatus("La cantidad de videos y subtítulos no coincide.", true);
      return;
    }
    if (videoFiles.length === 0) {
      showStatus("No hay archivos para renombrar.", true);
      return;
    }

    renameSubsBtn.disabled = true;
    renameVideosBtn.disabled = true;

    try {
      const resp = await fetch(API_RENAME, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({
          action,
          path,
          video_files: videoFiles,
          sub_files: subFiles,
        }),
      });
      const result = await resp.json();
      showStatus(result.message || (resp.ok ? "Renombrado exitoso." : "Error al renombrar."), !resp.ok);
      if (resp.ok) fetchAndDisplayFiles(path);
    } catch (err) {
      console.error("Error en el renombrado:", err);
      showStatus("Ocurrió un error inesperado. Revisá la consola del navegador.", true);
    } finally {
      renameSubsBtn.disabled = false;
      renameVideosBtn.disabled = false;
    }
  }

  renameSubsBtn.addEventListener("click", () => handleRename("rename_subtitles"));
  renameVideosBtn.addEventListener("click", () => handleRename("rename_videos"));

  refreshBtn.addEventListener("click", () => {
    const path = selectedPathInput.value;
    if (path) fetchAndDisplayFiles(path);
    else showStatus("No hay una carpeta seleccionada para refrescar.", true);
  });

  document.addEventListener("DOMContentLoaded", loadInitialTree);
  if (document.readyState !== "loading") loadInitialTree();
})();