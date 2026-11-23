(function () {
  const main = document.getElementById("main");
  const live = document.getElementById("live");
  const authSlot = document.getElementById("auth-slot");
  const config = window.LAYER_MANAGER_CONFIG;

  function el(tag, attrs) {
    const node = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (key) {
      if (key === "text") node.textContent = attrs[key];
      else if (key === "className") node.className = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    for (let i = 2; i < arguments.length; i += 1) {
      const child = arguments[i];
      if (child == null) continue;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  }

  function say(text) {
    live.textContent = text;
  }

  if (!config || !config.authMode) {
    main.textContent = "";
    main.appendChild(el("section", { className: "panel gate" },
      el("h2", { text: "Console is not configured" }),
      el("p", { text: "config.js is missing. This page has no embedded layer inventory and will not call the registry." })
    ));
    return;
  }

  const storageKey = "geoMapLayerManagerActor";
  const tokenKey = "geoMapLayerManagerToken";
  let actor = null;
  let layers = [];
  let selected = null;
  let statusNote = "";

  async function api(method, path, body) {
    return window.LayerManagerClient.request(config, sessionStorage, fetch, method, path, body);
  }

  function signedIn() {
    if (config.authMode === "local-fixture") return Boolean(sessionStorage.getItem(storageKey));
    return Boolean(sessionStorage.getItem(tokenKey));
  }

  function setNotice(text) {
    const node = document.getElementById("notice");
    if (!node) return;
    node.textContent = text || "";
    node.hidden = !text;
  }

  function setChrome(title, subtitle, nav) {
    document.getElementById("crumb").textContent = title;
    document.getElementById("crumb-sub").textContent = subtitle;
    ["layers", "build", "preview"].forEach(function (name) {
      const link = document.getElementById("nav-" + name);
      if (!link) return;
      if (name === nav) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function renderAuth() {
    authSlot.textContent = "";
    if (!signedIn()) {
      authSlot.appendChild(el("span", { className: "note", text: "Sign-in required" }));
      return;
    }
    const roleName = !actor ? "Signed in" : actor.role === "layer-admin" ? "Admin" : actor.role === "layer-reader" ? "Reader" : actor.role;
    const label = roleName + (actor && actor.synthetic_identity ? " · fixture" : "");
    authSlot.appendChild(el("span", { className: "chip", text: label }));
    const button = el("button", { className: "secondary", type: "button", text: "Sign out" });
    button.addEventListener("click", function () {
      sessionStorage.removeItem(storageKey);
      sessionStorage.removeItem(tokenKey);
      actor = null;
      setNotice("");
      location.hash = "#/layers";
      render();
    });
    authSlot.appendChild(button);
  }

  function renderGate() {
    main.textContent = "";
    setChrome("Sign in", "Access is required before any registry data is requested", "layers");
    const section = el("section", { className: "panel gate" },
      el("h2", { text: "Sign in" }),
      el("p", { className: "lede", text: "This console shows layer metadata only after sign-in. There is no open signup on this page, and password recovery is not handled here." })
    );
    if (config.authMode === "local-fixture") {
      section.appendChild(el("p", { text: "This local process accepts two labeled fixture identities. They are not staging credentials." }));
      const actions = el("div", { className: "actions" });
      ["fixture-admin", "fixture-reader"].forEach(function (name) {
        const button = el("button", { type: "button", text: "Continue as " + name });
        if (name === "fixture-reader") button.className = "secondary";
        button.addEventListener("click", function () {
          sessionStorage.setItem(storageKey, name);
          bootSession();
        });
        actions.appendChild(button);
      });
      section.appendChild(actions);
    } else if (config.cognito && config.cognito.clientId) {
      const button = el("button", { type: "button", text: "Sign in" });
      button.addEventListener("click", startHostedUi);
      section.appendChild(el("p", { className: "note", text: "Sign-in opens the existing hosted page, including its current MFA step." }));
      section.appendChild(el("div", { className: "actions" }, button));
    } else {
      section.appendChild(el("p", { text: "Cognito is not configured in config.js. The console will not invent an identity." }));
    }
    main.appendChild(section);
  }

  async function startHostedUi() {
    const verifier = window.LayerManagerAuth.randomVerifier();
    const challenge = await window.LayerManagerAuth.challengeS256(verifier);
    const state = window.LayerManagerAuth.randomVerifier();
    sessionStorage.setItem("geoMapPkceVerifier", verifier);
    sessionStorage.setItem("geoMapPkceState", state);
    location.assign(window.LayerManagerAuth.hostedUiUrl(config.cognito, config.cognito.redirectUri, state, challenge));
  }

  async function finishHostedUi() {
    const params = new URLSearchParams(location.search);
    const code = params.get("code");
    if (!code || config.authMode !== "apigateway-cognito") return;
    const state = params.get("state");
    if (!state || state !== sessionStorage.getItem("geoMapPkceState")) {
      say("Sign-in state did not match. No token was stored.");
      return;
    }
    const verifier = sessionStorage.getItem("geoMapPkceVerifier");
    const body = new URLSearchParams();
    body.set("grant_type", "authorization_code");
    body.set("client_id", config.cognito.clientId);
    body.set("code", code);
    body.set("redirect_uri", config.cognito.redirectUri);
    body.set("code_verifier", verifier);
    const response = await fetch(config.cognito.hostedUiBase + "/oauth2/token", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: body.toString()
    });
    if (!response.ok) {
      say("Cognito did not return a token.");
      return;
    }
    const token = await response.json();
    sessionStorage.setItem(tokenKey, token.access_token);
    history.replaceState({}, "", location.pathname);
  }

  function route() {
    const hash = location.hash || "#/layers";
    const parts = hash.replace(/^#\//, "").split("/");
    if (parts[0] === "preview") return { name: "preview" };
    if (parts[0] === "build") return { name: "build" };
    if (parts[0] === "register") return { name: "register" };
    if (parts[0] === "import") return { name: "import" };
    if (parts[0] === "layers" && parts.length > 1) {
      return { name: "detail", tag: decodeURIComponent(parts.slice(1).join("/")) };
    }
    return { name: "layers" };
  }

  async function render() {
    renderAuth();
    if (!signedIn()) {
      renderGate();
      return;
    }
    const current = route();
    if ((current.name === "build" || current.name === "preview") && window.LayerManagerBuild) {
      setChrome(
        current.name === "preview" ? "Preview" : "Datasets",
        current.name === "preview" ? "One allowlisted renderer image" : "Builds stay off until a source is allowed",
        current.name
      );
      return window.LayerManagerBuild.render({ main: main, api: api, el: el, say: say, actor: actor, view: current.name });
    }
    if (current.name === "register") return renderRegister();
    if (current.name === "import") return renderImport();
    if (current.name === "detail") return renderDetail(current.tag);
    return renderList();
  }

  async function renderList() {
    main.textContent = "";
    setChrome("Layers", "Registered metadata. Synthetic rows are labeled.", "layers");
    const search = el("input", { id: "layer-search", type: "search", placeholder: "Search by tag or title" });
    search.addEventListener("input", function () { loadList(search.value); });
    const body = el("tbody", { id: "layer-list" });
    body.appendChild(el("tr", {}, el("td", { colspan: "3", className: "loading", text: "Loading layers." })));
    const table = el("table", {},
      el("thead", {}, el("tr", {},
        el("th", { scope: "col", text: "Layer" }),
        el("th", { scope: "col", text: "Backend" }),
        el("th", { scope: "col", text: "Status" })
      )),
      body
    );
    const catalog = el("section", { className: "panel", "aria-label": "Layer catalog" },
      el("label", { for: "layer-search", text: "Search layers" }),
      search,
      table
    );
    const head = el("div", { className: "page-head" },
      el("p", { className: "note", text: "Open a row for zooms, bounds, style, and validation." })
    );
    if (!actor || actor.role === "layer-admin") {
      head.appendChild(el("div", { className: "actions" },
        linkButton("Register a layer", "#/register"),
        linkButton("Import legacy metadata", "#/import", true)
      ));
    }
    main.appendChild(head);
    main.appendChild(catalog);
    await loadList("");
    search.focus();
  }

  function linkButton(text, href, secondary) {
    const node = el("a", { className: secondary ? "button secondary" : "button", href: href, text: text });
    return node;
  }

  async function loadList(query) {
    const list = document.getElementById("layer-list");
    if (!list) return;
    const result = await api("GET", "/v1/layers?q=" + encodeURIComponent(query || ""));
    layers = result.layers;
    setNotice(result.inventory_note);
    list.textContent = "";
    if (!layers.length) {
      list.appendChild(el("tr", {}, el("td", { colspan: "3", text: "No layers match this search." })));
      return;
    }
    layers.forEach(function (layer) {
      const row = el("tr", { className: "clickable", tabindex: "0" });
      row.appendChild(el("td", {}, el("div", { className: "tag", text: layer.tag }), el("div", { text: layer.title })));
      row.appendChild(el("td", { text: layer.backend }));
      const status = el("td", {});
      status.appendChild(chips(layer, false));
      row.appendChild(status);
      function open() { location.hash = "#/layers/" + encodeURIComponent(layer.tag); }
      row.addEventListener("click", open);
      row.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
      });
      list.appendChild(row);
    });
  }

  function chips(layer, includeBackend) {
    const row = el("div", { className: "chips" });
    if (includeBackend !== false) row.appendChild(el("span", { className: "chip", text: layer.backend }));
    row.appendChild(el("span", { className: "chip " + layer.status, text: layer.status }));
    if (layer.synthetic) row.appendChild(el("span", { className: "chip synthetic", text: "Synthetic fixture" }));
    return row;
  }

  async function renderDetail(tag) {
    main.textContent = "";
    let result;
    try {
      result = await api("GET", "/v1/layers/item?tag=" + encodeURIComponent(tag));
    } catch (error) {
      main.appendChild(el("section", { className: "panel" }, el("h2", { text: "Layer not found" }), el("p", { text: error.message })));
      return;
    }
    selected = result.layer;
    setChrome(selected.title, selected.tag, "layers");
    const head = el("section", { className: "panel detail" },
      el("p", {}, el("a", { href: "#/layers", text: "Back to layers" })),
      el("h2", { id: "layer-title", tabindex: "-1", text: selected.title }),
      chips(selected),
      el("p", { className: "note", text: "Revision " + selected.revision + ". Updated " + selected.updated_at + "." })
    );
    head.appendChild(metaTable(selected));
    head.appendChild(ramp(selected));
    head.appendChild(issues(selected));
    head.appendChild(sources(selected));
    const tile = el("details", {}, el("summary", { text: "Tile address" }));
    tile.appendChild(el("p", { className: "note", text: result.preview.reason }));
    if (result.preview.template) {
      tile.appendChild(el("p", { className: "tag", text: result.preview.template }));
      tile.appendChild(el("p", { className: "note", text: "Shown as text only. The admin token is not sent to the tile backend." }));
    }
    head.appendChild(tile);
    if (actor && actor.role === "layer-admin") {
      head.appendChild(editForm(selected));
      if (selected.status === "draft") head.appendChild(publishForm(selected));
    }
    head.appendChild(exportForm(selected.tag));
    head.appendChild(await auditBlock(selected.tag));
    main.appendChild(head);
    document.getElementById("layer-title").focus();
    say("Showing " + selected.tag);
  }

  function metaTable(layer) {
    const pyramid = layer.pyramid || {};
    const cog = layer.cog || {};
    const bounds = layer.bounds;
    const rows = [
      ["Backend", layer.backend],
      ["PNG layout", pyramid.layout || "—"],
      ["Zooms", (pyramid.processed_levels || []).join(", ") || "none recorded"],
      ["Tile pixels", pyramid.tile_pixel_size == null ? "—" : String(pyramid.tile_pixel_size)],
      ["Tile merge / block", pyramid.tile_merge == null ? "—" : String(pyramid.tile_merge)],
      ["COG block size", cog.block_size ? cog.block_size.join(" × ") : "—"],
      ["COG overviews", (cog.overview_levels || []).join(", ") || "—"],
      ["Bounds", bounds ? bounds.crs + " " + bounds.minx + ", " + bounds.miny + " / " + bounds.maxx + ", " + bounds.maxy : "not set"],
      ["Nodata min / max", formatPair(layer.nodata.min_value, layer.nodata.max_value)],
      ["Fill nodata / raster", formatPair(layer.nodata.fill_nodata, layer.nodata.raster_nodata)]
    ];
    const list = el("dl", { className: "facts" });
    rows.forEach(function (row) {
      list.appendChild(el("div", {}, el("dt", { text: row[0] }), el("dd", { text: row[1] })));
    });
    return list;
  }

  function formatPair(a, b) {
    return (a == null ? "—" : String(a)) + " / " + (b == null ? "—" : String(b));
  }

  function ramp(layer) {
    const stops = (layer.style && layer.style.stops) || [];
    const bar = el("div", { className: "ramp", role: "img", "aria-label": "Color ramp" });
    if (!stops.length) return el("div", {}, el("h3", { text: "Style" }), el("p", { text: "No color stops yet." }));
    stops.forEach(function (stop) {
      const color = "rgba(" + stop.rgba.join(",") + ")";
      const swatch = el("span", { title: String(stop.value) });
      swatch.style.background = color;
      bar.appendChild(swatch);
    });
    return el("div", {}, el("h3", { text: "Style" }), bar);
  }

  function issues(layer) {
    const box = el("div", {}, el("h3", { text: "Validation" }));
    const validation = layer.validation;
    const list = el("ul", { className: "issues" });
    validation.errors.concat(validation.publish_blockers).forEach(function (item) {
      list.appendChild(el("li", { className: "error", text: item.field + ": " + item.message }));
    });
    validation.warnings.forEach(function (item) {
      list.appendChild(el("li", { className: "warning", text: item.field + ": " + item.message }));
    });
    if (!list.childNodes.length) list.appendChild(el("li", { text: "No validation issues." }));
    box.appendChild(list);
    return box;
  }

  function sources(layer) {
    const box = el("div", {}, el("h3", { text: "Source revisions" }));
    if (!layer.source_revisions.length) {
      box.appendChild(el("p", { text: "No source revisions recorded." }));
      return box;
    }
    const list = el("ul", {});
    layer.source_revisions.forEach(function (source) {
      list.appendChild(el("li", {}, el("span", { className: "tag", text: source.uri }), " — " + source.note + " (" + source.recorded_at + ")"));
    });
    box.appendChild(list);
    return box;
  }

  function editForm(layer) {
    const form = el("form", {}, el("h3", { text: "Edit metadata" }));
    const title = field(form, "Title", "edit-title", layer.title);
    form.appendChild(el("p", { className: "note", text: "Saving writes a new registry revision. It does not regenerate PNGs." }));
    const button = el("button", { type: "submit", text: "Save registry revision" });
    form.appendChild(el("div", { className: "actions" }, button));
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      const body = {
        tag: layer.tag,
        expected_revision: layer.revision,
        layer: { title: title.value }
      };
      try {
        const result = await api("PATCH", "/v1/layers/item?tag=" + encodeURIComponent(layer.tag), body);
        say(result.effects.png_pyramid_regenerated ? "Unexpected tile write" : "Saved revision " + result.layer.revision + ". PNG pyramids were not regenerated.");
        renderDetail(layer.tag);
      } catch (error) {
        say(error.message);
      }
    });
    return form;
  }

  function publishForm(layer) {
    const form = el("form", {}, el("h3", { text: "Publish registry record" }));
    form.appendChild(el("p", { text: "Publishing marks this draft in the registry. Existing PNG pyramids are not regenerated." }));
    const phrase = field(form, "Type publish-registry-only to confirm", "publish-phrase", "");
    const button = el("button", { type: "submit", text: "Publish registry record" });
    form.appendChild(el("div", { className: "actions" }, button));
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      try {
        const result = await api("POST", "/v1/layers/item/publish?tag=" + encodeURIComponent(layer.tag), {
          tag: layer.tag,
          expected_revision: layer.revision,
          confirmation: phrase.value.trim()
        });
        say("Published revision " + result.layer.revision + ". PNG pyramids were not regenerated.");
        renderDetail(layer.tag);
      } catch (error) {
        say(error.message);
      }
    });
    return form;
  }

  function exportForm(tag) {
    const box = el("details", {}, el("summary", { text: "Legacy export" }));
    box.appendChild(el("p", { className: "note", text: "Export returns setting.ini JSON and color.txt in the page. It does not write the tile repository." }));
    const out = el("textarea", { id: "legacy-export", readonly: "readonly" });
    const button = el("button", { type: "button", text: "Show legacy export" });
    button.addEventListener("click", async function () {
      try {
        const result = await api("POST", "/v1/layers/export-legacy", { tag: tag });
        out.value = JSON.stringify(result.setting, null, 2) + "\n\n" + result.color_txt;
        say(result.written ? "Unexpected write" : "Export displayed. Nothing was written to the tile repository.");
      } catch (error) {
        say(error.message);
      }
    });
    box.appendChild(el("div", { className: "actions" }, button));
    box.appendChild(out);
    return box;
  }

  async function auditBlock(tag) {
    const result = await api("GET", "/v1/layers/audit?tag=" + encodeURIComponent(tag));
    const box = el("details", {}, el("summary", { text: "Audit trail" }));
    if (!result.audit.length) {
      box.appendChild(el("p", { text: "No audit events." }));
      return box;
    }
    const list = el("ul", {});
    result.audit.forEach(function (event) {
      list.appendChild(el("li", { text: event.action + " · revision " + event.to_revision + " · " + event.actor_sub + " · " + event.at }));
    });
    box.appendChild(list);
    return box;
  }

  function renderRegister() {
    main.textContent = "";
    setChrome("Register", "A draft is stored only after confirmation.", "layers");
    const form = el("form", { className: "panel" },
      el("h2", { text: "Register a layer" }),
      el("p", { className: "note", text: "Preview validates metadata and does not save it. Create stores a draft. Neither step generates tiles." })
    );
    const tag = field(form, "Tag", "reg-tag", "demo/example/y2026");
    const title = field(form, "Title", "reg-title", "");
    const backend = el("select", { id: "reg-backend" });
    ["png-pyramid", "cog"].forEach(function (value) {
      backend.appendChild(el("option", { value: value, text: value }));
    });
    form.appendChild(el("label", { for: "reg-backend", text: "Backend" }));
    form.appendChild(backend);
    const levels = field(form, "Processed zooms", "reg-levels", "3, 4, 5");
    const merge = field(form, "Tile merge or COG block", "reg-merge", "1");
    const preview = el("button", { type: "button", text: "Preview metadata" });
    const create = el("button", { type: "submit", text: "Create draft", disabled: "disabled" });
    const phrase = field(form, "Type create-draft to confirm", "reg-phrase", "");
    const report = el("div", { id: "preview-report" });
    form.appendChild(el("div", { className: "actions" }, preview, create));
    form.appendChild(report);
    let digest = null;
    function draftLayer() {
      const zooms = levels.value.split(/[^0-9]+/).filter(Boolean).map(Number);
      const size = Number(merge.value || "1");
      const png = backend.value === "png-pyramid";
      return {
        tag: tag.value.trim(),
        title: title.value.trim(),
        backend: backend.value,
        pyramid: png ? {
          layout: "version-2-tiles",
          tile_pixel_size: 256,
          tile_merge: size,
          min_static_level: zooms.length ? zooms[0] : 3,
          min_dynamic_level: zooms.length ? zooms[zooms.length - 1] : null,
          processed_levels: zooms,
          version: 2,
          aggregate: "median",
          persistent: true
        } : null,
        cog: png ? null : { block_size: [size, size], overview_levels: [2], href_note: "Reference only. The registry does not fetch or rewrite the COG." },
        bounds: null,
        style: { type: "color-ramp", stops: [] },
        nodata: { min_value: null, max_value: null, fill_nodata: null, raster_nodata: null },
        source_revisions: [],
        authorized_tile_template: null
      };
    }
    preview.addEventListener("click", async function () {
      try {
        const result = await api("POST", "/v1/layers/preview", { layer: draftLayer() });
        digest = result.content_digest;
        create.disabled = !digest;
        report.textContent = "";
        report.appendChild(el("h3", { text: "Preview" }));
        report.appendChild(el("p", { text: result.persisted ? "Unexpected save" : "Not saved. PNG pyramids were not regenerated." }));
        const list = el("ul", { className: "issues" });
        const validation = result.validation;
        validation.errors.concat(validation.publish_blockers, validation.warnings).forEach(function (item) {
          list.appendChild(el("li", { className: item.severity === "warning" ? "warning" : "error", text: item.message }));
        });
        if (!list.childNodes.length) list.appendChild(el("li", { text: "No issues." }));
        report.appendChild(list);
        say("Preview ready. Nothing was saved.");
      } catch (error) {
        digest = null;
        create.disabled = true;
        say(error.message);
      }
    });
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      try {
        const result = await api("POST", "/v1/layers", {
          confirmation: phrase.value.trim(),
          content_digest: digest,
          layer: draftLayer()
        });
        say("Draft " + result.layer.tag + " saved at revision " + result.layer.revision + ". PNGs were not regenerated.");
        location.hash = "#/layers/" + encodeURIComponent(result.layer.tag);
      } catch (error) {
        say(error.message);
      }
    });
    main.appendChild(form);
    title.focus();
  }

  function renderImport() {
    main.textContent = "";
    setChrome("Import", "Legacy text becomes a registry draft. Tile files are not written.", "layers");
    const form = el("form", { className: "panel" },
      el("h2", { text: "Import legacy metadata" }),
      el("p", { className: "note", text: "Paste setting.ini JSON and color.txt. Import creates a draft in this registry and does not write the tile repository. Existing tags are refused." })
    );
    const tag = field(form, "Tag", "import-tag", "");
    const setting = area(form, "setting.ini JSON", "import-setting");
    const color = area(form, "color.txt", "import-color");
    const phrase = field(form, "Type import-legacy-draft to confirm", "import-phrase", "");
    form.appendChild(el("div", { className: "actions" }, el("button", { type: "submit", text: "Import as draft" })));
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      try {
        const parsed = JSON.parse(setting.value);
        const result = await api("POST", "/v1/layers/import-legacy", {
          tag: tag.value.trim(),
          setting: parsed,
          color_txt: color.value,
          confirmation: phrase.value.trim()
        });
        say("Imported " + result.layer.tag + " as a draft. Legacy files were not written.");
        location.hash = "#/layers/" + encodeURIComponent(result.layer.tag);
      } catch (error) {
        say(error.message);
      }
    });
    main.appendChild(form);
  }

  function field(form, label, id, value) {
    const input = el("input", { id: id, value: value });
    form.appendChild(el("label", { for: id, text: label }));
    form.appendChild(input);
    return input;
  }

  function area(form, label, id) {
    const input = el("textarea", { id: id });
    form.appendChild(el("label", { for: id, text: label }));
    form.appendChild(input);
    return input;
  }

  async function bootSession() {
    if (!signedIn()) {
      actor = null;
      statusNote = "";
      setNotice("");
      render();
      return;
    }
    try {
      const result = await api("GET", "/v1/session");
      actor = result.actor;
      const tileNote = result.tile_backend && result.tile_backend.note ? " " + result.tile_backend.note : "";
      statusNote = result.effects_notice + tileNote;
      setNotice(result.banner);
      say(result.banner);
      render();
    } catch (error) {
      actor = null;
      sessionStorage.removeItem(storageKey);
      sessionStorage.removeItem(tokenKey);
      say(error.message);
      render();
    }
  }

  window.addEventListener("hashchange", render);
  const params = new URLSearchParams(location.search);
  if (config.authMode === "local-fixture" && params.get("autologin") === "1") {
    sessionStorage.setItem(storageKey, "fixture-admin");
  }
  finishHostedUi().then(bootSession);
})();
