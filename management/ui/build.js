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
    const main = ctx.main;
    const el = ctx.el;
    main.textContent = "";
    const page = el("section", { className: "panel" },
      el("h2", { text: "Dataset build and renderer preview" }),
      el("p", { className: "note", text: "A queued raster job writes version-2 PNG blocks in batches. The batch size of 32 is not the size of the pyramid. Staging stays off until an allowlisted source, output bucket, container image, and subnets are set. A local rasterio run is not an S3 build. Renderer preview, when enabled, uses the exact function ARN and does not publish the registry." })
    );
    const status = el("div", { id: "build-status" });
    const preview = el("div", { id: "renderer-preview" });
    const form = el("form", {},
      el("h3", { text: "Plan a stored PNG block pyramid" })
    );
    const source = el("select", { id: "build-source" });
    form.appendChild(el("label", { for: "build-source", text: "Configured dataset" }));
    form.appendChild(source);
    const prefix = el("p", { id: "build-prefix", className: "note", text: "No source prefix is configured." });
    form.appendChild(prefix);
    const key = field(el, form, "Object key under that prefix", "build-key", "");
    const tag = field(el, form, "Layer id", "build-tag", "demo/built/fixture");
    const zooms = field(el, form, "Stored zooms", "build-zooms", "2");
    const merge = field(el, form, "Block merge (1-8)", "build-merge", "1");
    const inspect = el("button", { type: "button", text: "Inspect metadata" });
    const planButton = el("button", { type: "button", text: "Estimate plan" });
    const queue = el("button", { type: "submit", text: "Queue build", disabled: "disabled" });
    const phrase = field(el, form, "Type queue-build to confirm", "build-phrase", "");
    const report = el("div", { id: "build-report" });
    form.appendChild(el("div", { className: "actions" }, inspect, planButton, queue));
    form.appendChild(report);
    page.appendChild(status);
    page.appendChild(preview);
    page.appendChild(form);
    main.appendChild(page);

    const config = await call("GET", "/v1/builds/config");
    status.appendChild(el("p", { text: config.note }));
    status.appendChild(el("p", { text: "Real builds enabled: " + config.real_builds_enabled + ". Executor: " + config.executor + "." }));
    const sources = await call("GET", "/v1/builds/sources");
    sources.sources.forEach(function (item) {
      const label = item.kind === "s3" ? item.id + " prefix " + item.uri : item.title + " (" + item.kind + ", not an S3 object)";
      const option = el("option", { value: item.id, text: label });
      option.setAttribute("data-kind", item.kind);
      option.setAttribute("data-uri", item.uri || "");
      source.appendChild(option);
    });
    if (!sources.sources.length) {
      source.appendChild(el("option", { value: "", text: "No dataset is configured" }));
    }
    function selectedSource() {
      return source.options[source.selectedIndex] || null;
    }
    function showPrefix() {
      const current = selectedSource();
      if (!current || current.getAttribute("data-kind") !== "s3") {
        prefix.textContent = "This entry is not an S3 prefix. Metadata is not read from a bucket.";
        return;
      }
      prefix.textContent = "Only objects under " + current.getAttribute("data-uri") + " can be named. Other buckets are rejected.";
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
      try {
        const info = await call("POST", "/v1/builds/inspect", { source_id: current.value, key: key.value.trim() });
        report.appendChild(el("h3", { text: "Source metadata" }));
        report.appendChild(el("p", { text: "status " + (info.status || "ok") + ", read_s3 " + info.read_s3 + ", crs " + info.crs + ", nodata " + info.nodata + "." }));
        report.appendChild(el("p", { text: info.message || "Bounds were read from the object the configured reader returned." }));
      } catch (error) {
        report.appendChild(el("p", { text: error.message }));
      }
    });

    let digest = null;
    planButton.addEventListener("click", async function () {
      try {
        const plan = await call("POST", "/v1/builds/plan", draft());
        digest = plan.content_digest || null;
        queue.disabled = !plan.submittable;
        report.textContent = "";
        report.appendChild(el("h3", { text: "Approximate plan" }));
        report.appendChild(el("p", { text: "Blocks " + plan.tile_count + " in batches of " + plan.batch_size + " (absolute max " + plan.absolute_max + "). This is not a measured global pyramid." }));
        report.appendChild(el("p", { text: plan.submittable ? "This plan can be queued." : "Not queued. " + (plan.reason || "") }));
        ctx.say(plan.submittable ? "Plan ready. Nothing has been built." : "Plan was not queued.");
      } catch (error) {
        queue.disabled = true;
        ctx.say(error.message);
      }
    });
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      try {
        const result = await call("POST", "/v1/builds", Object.assign(draft(), {
          confirmation: phrase.value.trim(),
          idempotency_key: "ui-" + tag.value.trim()
        }));
        report.appendChild(el("p", { text: "Job " + result.job.job_id + " is " + result.job.status + ". Mode " + result.job.execution_mode + ". Real S3 write: " + result.job.real_s3_write + "." }));
        watch(result.job.job_id, report, el, ctx);
      } catch (error) {
        ctx.say(error.message);
      }
    });
    await showPreview(preview, el, ctx);
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
      report.appendChild(el("p", { text: "Job record: " + job.status + " " + job.progress.completed_tiles + "/" + job.progress.total_tiles + " (" + job.execution_mode + "). This page does not invent progress." }));
      if (job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
        ctx.say(job.status + ". Real S3 write: " + job.real_s3_write);
        return;
      }
      await new Promise(function (resolve) { setTimeout(resolve, 300); });
    }
  }

  async function showPreview(host, el, ctx) {
    host.appendChild(el("h3", { text: "Renderer preview" }));
    try {
      const status = await call("GET", "/v1/preview/status");
      host.appendChild(el("p", { text: status.note }));
      if (!status.enabled) return;
      const listing = await call("GET", "/v1/preview/layers");
      if (!listing.layers.length) {
        host.appendChild(el("p", { text: "The renderer allowlist is empty." }));
        return;
      }
      const layer = listing.layers[0];
      host.appendChild(el("p", { text: (layer.fixture ? "Fixture layer " : "Layer ") + layer.id + ". This image is not a build output and does not change the registry." }));
      const blob = await call("GET", "/v1/preview/tile?order=map&layer_id=" + encodeURIComponent(layer.id) + "&z=2&x=0&y=0");
      const url = URL.createObjectURL(blob);
      const image = el("img", { alt: "Renderer preview for " + layer.id, width: "128", height: "128" });
      image.src = url;
      host.appendChild(image);
    } catch (error) {
      host.appendChild(el("p", { text: error.message }));
      ctx.say(error.message);
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
