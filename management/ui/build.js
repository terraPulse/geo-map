(function (root) {
  function headers() {
    const value = { "content-type": "application/json" };
    const actor = sessionStorage.getItem("geoMapLayerManagerActor");
    const token = sessionStorage.getItem("geoMapLayerManagerToken");
    if (actor) value["x-layer-manager-fixture-actor"] = actor;
    if (token) value.authorization = "Bearer " + token;
    return value;
  }

  async function call(method, path, body) {
    const response = await fetch(path, { method: method, headers: headers(), body: body ? JSON.stringify(body) : undefined });
    const type = response.headers.get("content-type") || "";
    if (type.indexOf("image/png") === 0) {
      if (!response.ok) throw new Error("Preview image failed");
      return response.blob();
    }
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      const error = new Error((payload.error && payload.error.message) || "Request failed");
      error.payload = payload;
      throw error;
    }
    return payload.result;
  }

  async function render(ctx) {
    if (ctx.view === "preview") return renderPreview(ctx);
    return renderDatasets(ctx);
  }

  async function renderDatasets(ctx) {
    const main = ctx.main;
    const el = ctx.el;
    main.textContent = "";
    const status = el("div", { id: "build-status", className: "panel" },
      el("h2", { text: "Dataset builds" }),
      el("p", { className: "loading", text: "Checking whether builds are enabled." })
    );
    const formHost = el("div", { id: "build-form-host" });
    main.appendChild(el("div", { className: "stack" }, status, formHost));
    let config;
    try {
      config = await call("GET", "/v1/builds/config");
    } catch (error) {
      status.textContent = "";
      status.appendChild(el("h2", { text: "Dataset builds" }));
      status.appendChild(el("p", { className: "error", role: "alert", text: error.message }));
      return;
    }
    status.textContent = "";
    status.appendChild(el("h2", { text: "Dataset builds" }));
    const off = !config.real_builds_enabled;
    status.appendChild(el("p", {}, el("span", { className: off ? "chip off" : "chip published", text: off ? "Builds off" : "Builds enabled" }), " ", el("span", { className: "note", text: "Executor " + config.executor + "." })));
    status.appendChild(el("p", { className: "lede", text: "The selected test location is s3://geo-map-tiles-dev/tiles. Its format is still being inspected, so it is not a build source and nothing is queued against it." }));
    if (off) {
      status.appendChild(el("div", { className: "state" },
        el("strong", { text: "No build is running" }),
        el("span", { text: "Real builds stay off. This page does not invent job progress." })
      ));
    }
    const technical = el("details", {},
      el("summary", { text: "Build limits" }),
      el("p", { className: "note", text: config.note })
    );
    status.appendChild(technical);

    const sources = await call("GET", "/v1/builds/sources");
    if (!sources.sources.length) {
      formHost.appendChild(el("section", { className: "panel" },
        el("h2", { text: "Allowlisted sources" }),
        el("div", { className: "state" },
          el("strong", { text: "No dataset is configured" }),
          el("span", { text: "Only a configured source prefix can be planned. Arbitrary buckets are not accepted." })
        )
      ));
      return;
    }
    const form = el("form", { className: "panel" }, el("h2", { text: "Plan an allowlisted dataset" }));
    const source = el("select", { id: "build-source" });
    form.appendChild(el("label", { for: "build-source", text: "Configured dataset" }));
    form.appendChild(source);
    const prefix = el("p", { id: "build-prefix", className: "note", text: "" });
    form.appendChild(prefix);
    field(el, form, "Object key under that prefix", "build-key", "");
    field(el, form, "Layer id", "build-tag", "");
    field(el, form, "Stored zooms", "build-zooms", "2");
    field(el, form, "Block merge (1-8)", "build-merge", "1");
    const inspect = el("button", { type: "button", text: "Inspect metadata" });
    const planButton = el("button", { type: "button", className: "secondary", text: "Estimate plan" });
    const queue = el("button", { type: "submit", text: "Queue build", disabled: "disabled" });
    field(el, form, "Type queue-build to confirm", "build-phrase", "");
    const report = el("div", { id: "build-report" });
    form.appendChild(el("div", { className: "actions" }, inspect, planButton, queue));
    form.appendChild(report);
    sources.sources.forEach(function (item) {
      const label = item.kind === "s3" ? item.id + " · " + item.uri : item.title + " (" + item.kind + ")";
      const option = el("option", { value: item.id, text: label });
      option.setAttribute("data-kind", item.kind);
      option.setAttribute("data-uri", item.uri || "");
      source.appendChild(option);
    });
    function selectedSource() { return source.options[source.selectedIndex] || null; }
    function showPrefix() {
      const current = selectedSource();
      prefix.textContent = !current || current.getAttribute("data-kind") !== "s3"
        ? "This entry is not an S3 prefix. Metadata is not read from a bucket."
        : "Only objects under " + current.getAttribute("data-uri") + " can be named.";
    }
    source.addEventListener("change", showPrefix);
    showPrefix();
    inspect.addEventListener("click", async function () {
      const current = selectedSource();
      report.textContent = "";
      if (!current || current.getAttribute("data-kind") !== "s3") {
        report.appendChild(el("p", { text: "Inspect applies to a configured S3 prefix. No bucket was read." }));
        return;
      }
      report.appendChild(el("p", { className: "loading", text: "Reading metadata." }));
      try {
        const info = await call("POST", "/v1/builds/inspect", { source_id: current.value, key: document.getElementById("build-key").value.trim() });
        report.textContent = "";
        report.appendChild(el("p", { text: (info.message || "Metadata returned") + " CRS " + info.crs + ". S3 read: " + info.read_s3 + "." }));
      } catch (error) {
        report.textContent = "";
        report.appendChild(el("p", { className: "error", role: "alert", text: error.message }));
      }
    });
    planButton.addEventListener("click", async function () {
      report.textContent = "";
      report.appendChild(el("p", { className: "loading", text: "Estimating the plan." }));
      try {
        const plan = await call("POST", "/v1/builds/plan", draft());
        queue.disabled = !plan.submittable;
        report.textContent = "";
        report.appendChild(el("p", { text: plan.tile_count + " blocks, batch size " + plan.batch_size + ", absolute maximum " + plan.absolute_max + "." }));
        report.appendChild(el("p", { text: plan.submittable ? "This plan can be queued. Nothing has been built." : "Not queued. " + (plan.reason || "") }));
        ctx.say(plan.submittable ? "Plan ready. Nothing has been built." : "Plan was not queued.");
      } catch (error) {
        queue.disabled = true;
        report.textContent = "";
        report.appendChild(el("p", { className: "error", role: "alert", text: error.message }));
      }
    });
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      try {
        const result = await call("POST", "/v1/builds", Object.assign(draft(), {
          confirmation: document.getElementById("build-phrase").value.trim(),
          idempotency_key: "ui-" + document.getElementById("build-tag").value.trim()
        }));
        report.appendChild(el("p", { text: "Job " + result.job.job_id + " is " + result.job.status + ". Real S3 write: " + result.job.real_s3_write + "." }));
        watch(result.job.job_id, report, el, ctx);
      } catch (error) {
        ctx.say(error.message);
      }
    });
    formHost.appendChild(form);
  }

  async function renderPreview(ctx) {
    const main = ctx.main;
    const el = ctx.el;
    main.textContent = "";
    const copy = el("div", { className: "page-head" },
      el("h2", { text: "Tile preview" }),
      el("p", { className: "lede", text: "The image below is the renderer response for one allowlisted layer. It is not a build product and it does not change the registry." })
    );
    const stage = el("div", { className: "preview-stage", id: "renderer-preview" },
      el("p", { className: "loading", text: "Checking preview status." })
    );
    main.appendChild(el("section", { className: "panel" }, copy, stage));
    stage.textContent = "";
    try {
      const status = await call("GET", "/v1/preview/status");
      if (!status.enabled) {
        stage.appendChild(el("div", { className: "state" },
          el("strong", { text: "Preview is not configured" }),
          el("span", { text: status.note })
        ));
        return;
      }
      const listing = await call("GET", "/v1/preview/layers");
      if (!listing.layers.length) {
        stage.appendChild(el("div", { className: "state" },
          el("strong", { text: "No preview layer" }),
          el("span", { text: "The renderer allowlist is empty." })
        ));
        return;
      }
      const layer = listing.layers[0];
      const caption = el("p", { className: "note", text: layer.id + (layer.fixture ? " · fixture" : "") + ". " + status.note });
      const blob = await call("GET", "/v1/preview/tile?order=map&layer_id=" + encodeURIComponent(layer.id) + "&z=2&x=0&y=0");
      const url = URL.createObjectURL(blob);
      const image = el("img", { alt: "Renderer preview for " + layer.id });
      image.src = url;
      stage.appendChild(image);
      main.querySelector(".panel").appendChild(caption);
    } catch (error) {
      stage.appendChild(el("div", { className: "state" },
        el("strong", { text: "Preview unavailable" }),
        el("span", { className: "error", text: error.message })
      ));
      ctx.say(error.message);
    }
  }

  function draft() {
    return {
      source_id: document.getElementById("build-source").value,
      key: document.getElementById("build-key").value.trim() || undefined,
      tag: document.getElementById("build-tag").value.trim(),
      title: "Fixture build " + document.getElementById("build-tag").value.trim(),
      zooms: document.getElementById("build-zooms").value.split(/[^0-9]+/).filter(Boolean).map(Number),
      tile_merge: Number(document.getElementById("build-merge").value || "1"),
      aggregate: "median",
      resampling: "nearest"
    };
  }

  async function watch(jobId, report, el, ctx) {
    for (let i = 0; i < 20; i += 1) {
      const result = await call("GET", "/v1/builds/item?job_id=" + encodeURIComponent(jobId));
      const job = result.job;
      report.appendChild(el("p", { text: job.status + " · " + job.progress.completed_tiles + "/" + job.progress.total_tiles + ". Progress comes from the job record." }));
      if (job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
        ctx.say(job.status + ". Real S3 write: " + job.real_s3_write);
        return;
      }
      await new Promise(function (resolve) { setTimeout(resolve, 300); });
    }
  }

  function field(el, form, label, id, value) {
    const input = el("input", { id: id, value: value });
    form.appendChild(el("label", { for: id, text: label }));
    form.appendChild(input);
    return input;
  }

  root.LayerManagerBuild = { render: render };
})(window);
