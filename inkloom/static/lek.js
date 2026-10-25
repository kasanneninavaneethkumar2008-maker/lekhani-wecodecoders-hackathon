/* Lekhani shared page behaviour. Everything here is progressive enhancement:
   navigation links, the flowchart steps, and the forms all remain usable
   without JavaScript (the slide-free fallbacks are server-rendered). */
(function () {
  "use strict";

  document.documentElement.classList.add("js");

  /* ---- motion preference (site-level switch + OS setting) ------------------ */
  var reduceQuery = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false, addEventListener: null };
  var manualReduce = false;
  try {
    manualReduce = window.localStorage.getItem("lekhani-reduce-motion") === "1";
  } catch (error) {
    manualReduce = false; /* storage may be blocked; the switch still works */
  }
  var motionButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-reduce-motion]")
  );
  var motionListeners = [];

  /* True when either the visitor's OS setting or the site switch asks for
     less motion. CSS also keys off `html.reduce-motion`. */
  var prefersReducedMotion = function () {
    return manualReduce || !!reduceQuery.matches;
  };

  var applyMotionState = function () {
    var reduced = prefersReducedMotion();
    document.documentElement.classList.toggle("reduce-motion", reduced);
    motionButtons.forEach(function (button) {
      button.setAttribute("aria-pressed", reduced ? "true" : "false");
    });
    motionListeners.forEach(function (listener) { listener(reduced); });
  };

  motionButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      /* The OS setting always wins: when it asks for reduced motion, the
         switch can only add to that, never override the visitor's system. */
      manualReduce = reduceQuery.matches ? true : !prefersReducedMotion();
      try {
        window.localStorage.setItem("lekhani-reduce-motion", manualReduce ? "1" : "0");
      } catch (error) {
        /* Preference is not saved, but it applies for this page. */
      }
      applyMotionState();
    });
  });

  if (reduceQuery.addEventListener) {
    reduceQuery.addEventListener("change", applyMotionState);
  }

  /* ---- mobile navigation -------------------------------------------------- */
  var header = document.querySelector("[data-app-header]");
  var navToggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");

  function setNav(open) {
    if (!header || !navToggle) { return; }
    header.setAttribute("data-nav-open", open ? "true" : "false");
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (header && navToggle) {
    navToggle.addEventListener("click", function () {
      setNav(navToggle.getAttribute("aria-expanded") !== "true");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && navToggle.getAttribute("aria-expanded") === "true") {
        setNav(false);
        navToggle.focus();
      }
    });
    if (nav) {
      nav.addEventListener("click", function (event) {
        if (event.target.closest && event.target.closest("a")) { setNav(false); }
      });
    }
  }

  /* ---- guest dropdown (native details, with Escape support) --------------- */
  var guestMenu = document.querySelector("[data-guest-menu]");
  if (guestMenu) {
    var guestSummary = guestMenu.querySelector("summary");
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && guestMenu.open) {
        guestMenu.open = false;
        if (guestSummary) { guestSummary.focus(); }
      }
    });
    document.addEventListener("click", function (event) {
      if (guestMenu.open && !guestMenu.contains(event.target)) {
        guestMenu.open = false;
      }
    });
  }

  /* ---- preview forms never submit in this build --------------------------- */
  Array.prototype.forEach.call(document.querySelectorAll("[data-preview-form]"), function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
    });
  });

  /* ---- report form: privacy/security warning ------------------------------ */
  var category = document.querySelector("[data-issue-category]");
  var privacyWarning = document.getElementById("privacy-warning");
  if (category && privacyWarning) {
    var syncWarning = function () {
      privacyWarning.hidden = category.value !== "privacy-security";
    };
    category.addEventListener("change", syncWarning);
    syncWarning();
  }

  /* ---- About flowchart ---------------------------------------------------- */
  /* Calm, continuous highlight while the section is on-screen. There are no
     play/pause controls. Auto-cycling never moves focus and never overwrites
     an explanation the visitor selected: a node click pins that step until
     another selection. The cycle pauses off-screen and in hidden tabs, and is
     static for reduced-motion visitors. */
  var flow = document.querySelector("[data-flow]");
  if (flow) {
    var nodes = Array.prototype.slice.call(flow.querySelectorAll("[data-flow-node]"));
    var detailStep = document.querySelector("[data-flow-detail-step]");
    var detailTitle = document.querySelector("[data-flow-detail-title]");
    var detailText = document.querySelector("[data-flow-detail-text]");
    var CYCLE_MS = 2600;

    var active = 0;
    var visible = false;
    var pinned = false;
    var timer = null;

    var stop = function () {
      if (timer) { window.clearInterval(timer); timer = null; }
    };

    var setActive = function (index) {
      active = index;
      nodes.forEach(function (node, i) {
        node.setAttribute("aria-pressed", i === index ? "true" : "false");
      });
      if (detailStep) { detailStep.textContent = String(index + 1); }
      if (detailTitle) { detailTitle.textContent = nodes[index].getAttribute("data-title"); }
      if (detailText) { detailText.textContent = nodes[index].getAttribute("data-desc"); }
    };

    var start = function () {
      if (pinned || prefersReducedMotion() || !visible || document.hidden || timer) {
        return;
      }
      timer = window.setInterval(function () {
        if (!pinned) { setActive((active + 1) % nodes.length); }
      }, CYCLE_MS);
    };

    nodes.forEach(function (node, index) {
      node.addEventListener("click", function () {
        pinned = true; /* keep the visitor's choice; never overwrite it */
        setActive(index);
      });
    });

    motionListeners.push(function (reduced) {
      if (reduced) { stop(); } else { start(); }
    });

    var handleVisibility = function () {
      if (document.hidden) { stop(); } else { start(); }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("pagehide", stop);

    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          visible = entry.isIntersecting;
          if (visible) { start(); } else { stop(); }
        });
      }, { threshold: 0.25 });
      observer.observe(flow);
    } else {
      visible = true;
      start();
    }

    setActive(0);
    applyMotionState();
  } else {
    applyMotionState();
  }

  /* ---- workspace: stale results and unsaved-work warnings -----------------
     The workspace is server-rendered; this script only enhances it. Draft
     text never enters innerHTML: preview highlights are rendered by the
     server as escaped text segments, and every dynamic string here is set
     with textContent. Checks are synchronous server round-trips, so a result
     can never arrive asynchronously after the inputs changed — the page only
     ever receives findings for the exact text it submitted.
     ------------------------------------------------------------------------ */
  var workspace = document.querySelector("[data-workspace]");
  if (workspace) {
    var draftForm = workspace.querySelector("[data-workspace-form]");
    var bodyField = document.getElementById("draft-body");
    var typeField = document.getElementById("draft-type");
    var audienceField = document.getElementById("draft-audience");
    var titleField = document.getElementById("draft-title");
    var importForm = document.getElementById("ws-import-form");
    var fileForm = document.getElementById("ws-file-form");
    var fileInput = document.getElementById("draft-file");
    var preview = workspace.querySelector("[data-preview]");
    var staleNotice = workspace.querySelector("[data-editor-stale]");
    var statusEl = workspace.querySelector("[data-check-status]");
    var statusDetail = workspace.querySelector("[data-status-detail]");
    var announcer = workspace.querySelector("[data-announcer]");
    var runButton = workspace.querySelector("[data-run-checks]");
    var runHint = document.getElementById("run-hint");
    var wordCount = workspace.querySelector("[data-word-count]");
    var charCount = workspace.querySelector("[data-char-count]");
    var noteField = document.getElementById("review-note");
    var reviewCard = workspace.querySelector("[data-review-card]");
    var reviewStale = workspace.querySelector("[data-review-stale-live]");
    var reviewLive = workspace.querySelector("[data-review-live]");
    var submitting = false;
    var lastStale = null;

    /* The preview is the exact checked snapshot; its textContent is the text
       the server checked (line endings normalised to LF on the server). */
    var checkedText = preview ? preview.textContent : null;
    var checkedType = workspace.getAttribute("data-check-type") || "";
    var checkedAudience = workspace.getAttribute("data-check-audience") || "";
    var serverStatus = workspace.getAttribute("data-status") || "not-checked";

    var announce = function (message) {
      if (announcer) { announcer.textContent = message; }
    };

    var snapshotIsCurrent = function () {
      if (checkedText === null || !bodyField) { return false; }
      return bodyField.value === checkedText
        && (!typeField || typeField.value === checkedType)
        && (!audienceField || audienceField.value === checkedAudience);
    };

    var setStatus = function (key, label, detail) {
      if (!statusEl) { return; }
      statusEl.setAttribute("data-status", key);
      statusEl.textContent = label;
      workspace.setAttribute("data-status", key);
      if (statusDetail && detail) { statusDetail.textContent = detail; }
    };

    var setRunLabel = function (hasCheck) {
      if (!runButton || submitting) { return; }
      runButton.textContent = hasCheck ? "Run checks again →" : "Run checks →";
    };

    var updateCounts = function () {
      if (!bodyField) { return; }
      var value = bodyField.value;
      var words = value.match(/\S+/g);
      if (wordCount) { wordCount.textContent = String(words ? words.length : 0); }
      if (charCount) { charCount.textContent = String(value.length); }
    };

    /* The auxiliary forms carry a copy of the draft and the active rule-set
       mode so a rejected import can re-render the desk without losing work. */
    var carriedForms = [importForm, fileForm].filter(function (form) { return !!form; });
    var syncImportFields = function () {
      if (!draftForm || !draftForm.elements) { return; }
      ["title", "body", "content_type", "audience", "notes", "rule_mode"].forEach(function (name) {
        var source = draftForm.elements[name];
        if (!source) { return; }
        carriedForms.forEach(function (form) {
          var target = form.elements[name];
          if (target) { target.value = source.value; }
        });
      });
    };

    var syncRunState = function () {
      if (!runButton || !bodyField || submitting) { return; }
      var empty = !bodyField.value.trim();
      runButton.disabled = empty;
      runButton.setAttribute("aria-disabled", empty ? "true" : "false");
      if (runHint) { runHint.hidden = !empty; }
    };

    /* Reflect draft changes immediately: results are labelled outdated, the
       preview is kept as the checked snapshot, and replacement is refused. */
    var markStale = function () {
      if (checkedText === null) { return; }
      var current = snapshotIsCurrent();
      if (lastStale !== null && current === lastStale) { return; }
      if (current) {
        setStatus(serverStatus === "incomplete" ? "incomplete" : "checked",
                  serverStatus === "incomplete" ? "Check incomplete" : "Checked",
                  "This draft matches the checked snapshot.");
        setRunLabel(true);
      } else {
        setStatus("changes", "Changes since check",
                  "The draft, content type, or audience changed after the last check.");
        setRunLabel(true);
      }
      if (staleNotice) { staleNotice.hidden = current; }
      if (reviewCard) { reviewCard.hidden = !current; }
      if (reviewStale) { reviewStale.hidden = current || !reviewCard; }
      if (lastStale !== current) {
        announce(current
          ? "The draft matches the checked snapshot again."
          : "Draft changed. Results are out of date. Run checks again.");
        lastStale = current;
      }
    };

    if (draftForm) {
      draftForm.addEventListener("input", function (event) {
        if (event.target === bodyField) { updateCounts(); }
        syncImportFields();
        syncRunState();
        markStale();
      });
      draftForm.addEventListener("change", function () {
        syncImportFields();
        syncRunState();
        markStale();
      });
    }
    updateCounts();
    syncImportFields();
    syncRunState();

    /* ---- editor view: Edit / Check preview ------------------------------- */
    var viewTabs = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-editor-tab]")
    );
    var viewPanels = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-editor-view]")
    );
    var showView = function (name) {
      viewTabs.forEach(function (tab) {
        var active = tab.getAttribute("data-editor-tab") === name;
        tab.setAttribute("aria-selected", active ? "true" : "false");
        tab.tabIndex = active ? 0 : -1;
      });
      viewPanels.forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-editor-view") !== name;
      });
    };
    viewTabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () {
        showView(tab.getAttribute("data-editor-tab"));
      });
      tab.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") { return; }
        event.preventDefault();
        var next = (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length)
          % viewTabs.length;
        viewTabs[next].focus();
        showView(viewTabs[next].getAttribute("data-editor-tab"));
      });
    });

    /* ---- mobile panels: Write / Findings / Evidence ---------------------- */
    var panelTabs = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-ws-tab]")
    );
    var panels = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-ws-panel]")
    );
    var narrow = window.matchMedia
      ? window.matchMedia("(max-width: 1100px)")
      : { matches: false };
    var activatePanel = function (name, moveFocus) {
      panelTabs.forEach(function (tab) {
        var active = tab.getAttribute("data-ws-tab") === name;
        tab.setAttribute("aria-selected", active ? "true" : "false");
        tab.tabIndex = active ? 0 : -1;
      });
      panels.forEach(function (panel) {
        panel.classList.toggle(
          "is-active", panel.getAttribute("data-ws-panel") === name
        );
      });
      if (moveFocus) {
        var tab = panelTabs.filter(function (item) {
          return item.getAttribute("data-ws-tab") === name;
        })[0];
        if (tab) { tab.focus(); }
      }
    };
    if (panels.length) { panels[0].classList.add("is-active"); }
    if (panelTabs.length) {
      panelTabs.forEach(function (tab, index) {
        tab.addEventListener("click", function () {
          activatePanel(tab.getAttribute("data-ws-tab"));
        });
        tab.addEventListener("keydown", function (event) {
          if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") { return; }
          event.preventDefault();
          var next = (index + (event.key === "ArrowRight" ? 1 : -1)
            + panelTabs.length) % panelTabs.length;
          panelTabs[next].focus();
          activatePanel(panelTabs[next].getAttribute("data-ws-tab"));
        });
      });
    }

    /* ---- findings selection and rule evidence ---------------------------- */
    var findingButtons = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-finding]")
    );
    var evidencePanels = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-evidence]")
    );
    var evidenceEmpty = workspace.querySelector("[data-evidence-empty]");
    var marks = Array.prototype.slice.call(
      workspace.querySelectorAll(".ws-mark")
    );
    var selectedFinding = null;

    var selectFinding = function (ruleId) {
      selectedFinding = ruleId;
      findingButtons.forEach(function (button) {
        button.setAttribute(
          "aria-pressed", button.getAttribute("data-finding") === ruleId
            ? "true" : "false"
        );
      });
      var target = null;
      evidencePanels.forEach(function (panel) {
        var match = panel.getAttribute("data-evidence") === ruleId;
        panel.hidden = !match;
        if (match) { target = panel; }
      });
      if (evidenceEmpty) { evidenceEmpty.hidden = true; }
      var firstMark = null;
      marks.forEach(function (mark) {
        var ids = (mark.getAttribute("data-rule-ids") || "").split(/\s+/);
        var match = ids.indexOf(ruleId) !== -1;
        mark.classList.toggle("is-selected", match);
        mark.classList.toggle("is-dim", ids.length > 0 && !match);
        if (match && !firstMark) { firstMark = mark; }
      });

      if (narrow.matches) {
        /* The finding button is now hidden with its panel, so move focus to
           the evidence the visitor explicitly asked to inspect. */
        activatePanel("evidence", false);
        if (target) { target.focus({ preventScroll: true }); }
      } else if (firstMark) {
        showView("preview");
        if (firstMark.scrollIntoView) {
          firstMark.scrollIntoView({
            block: "nearest",
            behavior: prefersReducedMotion() ? "auto" : "smooth"
          });
        }
      }
    };

    findingButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        selectFinding(button.getAttribute("data-finding"));
      });
    });

    Array.prototype.forEach.call(
      workspace.querySelectorAll("[data-back-findings]"),
      function (backButton) {
        backButton.addEventListener("click", function (event) {
          event.preventDefault();
          var article = backButton.closest("[data-evidence]");
          var ruleId = article
            ? article.getAttribute("data-evidence") : selectedFinding;
          activatePanel("findings");
          var current = findingButtons.filter(function (button) {
            return button.getAttribute("data-finding") === ruleId;
          })[0];
          if (current) { current.focus(); }
        });
      }
    );

    /* ---- category filters ------------------------------------------------ */
    var filterButtons = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-filter]")
    );
    var findingItems = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-finding-item]")
    );
    filterButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        var category = button.getAttribute("data-filter");
        filterButtons.forEach(function (item) {
          item.setAttribute(
            "aria-pressed", item === button ? "true" : "false"
          );
        });
        var shown = 0;
        findingItems.forEach(function (item) {
          var visible = category === "all"
            || item.getAttribute("data-category") === category;
          item.hidden = !visible;
          if (visible) { shown += 1; }
        });
        announce(shown + " finding" + (shown === 1 ? "" : "s") + " shown.");
      });
    });

    /* ---- controlled terminology replacement ----------------------------- */
    var replaceUrl = workspace.getAttribute("data-replace-url") || "";
    var replacePanels = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-replace]")
    );

    var replaceMessage = function (panel, message) {
      var status = panel.querySelector("[data-replace-status]");
      if (status) { status.textContent = message; }
      announce(message);
    };

    replacePanels.forEach(function (panel) {
      var select = panel.querySelector("[data-occurrence]");
      var previewButton = panel.querySelector("[data-preview-replace]");
      var previewBox = panel.querySelector("[data-replace-preview]");
      var beforeText = panel.querySelector("[data-before]");
      var afterText = panel.querySelector("[data-after]");
      var applyButton = panel.querySelector("[data-apply-replace]");
      var undoButton = panel.querySelector("[data-undo-replace]");
      var replacement = panel.getAttribute("data-replacement") || "";
      var ruleId = panel.getAttribute("data-rule-id") || "";
      var pending = null;
      var previousBody = null;

      var occurrence = function () {
        if (!select || !select.value) { return null; }
        var parts = select.value.split(":");
        var start = parseInt(parts[0], 10);
        var end = parseInt(parts[1], 10);
        if (isNaN(start) || isNaN(end)) { return null; }
        return { start: start, end: end };
      };

      if (previewButton) {
        previewButton.addEventListener("click", function () {
          var span = occurrence();
          if (!span || checkedText === null) {
            replaceMessage(panel, "Run checks again to locate this occurrence.");
            return;
          }
          if (!snapshotIsCurrent()) {
            replaceMessage(panel,
              "The draft no longer matches the checked snapshot. Run checks again " +
              "before previewing a replacement.");
            return;
          }
          var before = checkedText.slice(span.start, span.end);
          if (!before) {
            replaceMessage(panel, "That occurrence is no longer present in the checked text.");
            return;
          }
          pending = { start: span.start, end: span.end, before: before };
          if (beforeText) { beforeText.textContent = before; }
          if (afterText) { afterText.textContent = replacement; }
          if (previewBox) { previewBox.hidden = false; }
          replaceMessage(panel, "Preview only. Nothing has changed yet.");
        });
      }

      if (applyButton) {
        applyButton.addEventListener("click", function () {
          if (!pending) {
            replaceMessage(panel, "Preview the replacement before applying it.");
            return;
          }
          if (!snapshotIsCurrent()) {
            replaceMessage(panel,
              "Replacement refused: the draft changed after the check. Run checks " +
              "again first.");
            return;
          }
          var confirmed = window.confirm(
            "Replace \u201c" + pending.before + "\u201d with \u201c" + replacement +
            "\u201d in this single occurrence?"
          );
          if (!confirmed) { return; }
          var fingerprintField = draftForm
            ? draftForm.querySelector("input[name='check_fingerprint']") : null;
          if (!replaceUrl || !fingerprintField) {
            replaceMessage(panel, "Replacement is unavailable on this page.");
            return;
          }
          var csrfMeta = document.querySelector('meta[name="csrf-token"]');
          var csrfInput = draftForm ? draftForm.querySelector("input[name='csrf_token']") : null;
          var csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : (csrfInput ? csrfInput.value : "");
          applyButton.disabled = true;
          window.fetch(replaceUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Accept": "application/json",
              "X-CSRF-Token": csrfToken
            },
            credentials: "same-origin",
            body: JSON.stringify({
              body: bodyField.value,
              rule_id: ruleId,
              start: pending.start,
              end: pending.end,
              content_type: typeField ? typeField.value : "",
              rule_mode: workspace.getAttribute("data-rule-mode") || "workspace",
              check_fingerprint: fingerprintField.value,
              csrf_token: csrfToken
            })
          }).then(function (response) {
            return response.json().then(function (data) {
              return { ok: response.ok, data: data };
            });
          }).then(function (result) {
            applyButton.disabled = false;
            if (!result.ok || !result.data.ok) {
              replaceMessage(panel, result.data.message || "The replacement was refused.");
              return;
            }
            previousBody = bodyField.value;
            bodyField.value = result.data.body;
            updateCounts();
            pending = null;
            if (previewBox) { previewBox.hidden = true; }
            if (undoButton) { undoButton.hidden = false; }
            markStale();
            replaceMessage(panel, result.data.message ||
              "Replaced one occurrence. Run checks again to refresh the findings.");
          }).catch(function () {
            applyButton.disabled = false;
            replaceMessage(panel, "The replacement could not be completed. Try again.");
          });
        });
      }

      if (undoButton) {
        undoButton.addEventListener("click", function () {
          if (previousBody === null) { return; }
          bodyField.value = previousBody;
          previousBody = null;
          undoButton.hidden = true;
          updateCounts();
          markStale();
          replaceMessage(panel,
            "Replacement undone. The draft is back to the text from before the replacement.");
        });
      }
    });

    /* ---- expand editor --------------------------------------------------- */
    var expandButton = workspace.querySelector("[data-expand-editor]");
    var setExpanded = function (expanded) {
      workspace.classList.toggle("is-editor-expanded", expanded);
      if (expandButton) {
        expandButton.setAttribute("aria-expanded", expanded ? "true" : "false");
        expandButton.textContent = expanded ? "Close expanded editor" : "Expand editor";
      }
    };
    if (expandButton) {
      expandButton.addEventListener("click", function () {
        var expanded = !workspace.classList.contains("is-editor-expanded");
        setExpanded(expanded);
        if (expanded && bodyField) { bodyField.focus(); }
      });
    }

    /* ---- start options, file import, and drag and drop ------------------- */
    Array.prototype.forEach.call(
      workspace.querySelectorAll("[data-focus-editor]"),
      function (link) {
        link.addEventListener("click", function (event) {
          if (!bodyField) { return; }
          event.preventDefault();
          bodyField.focus();
          if (bodyField.scrollIntoView) {
            bodyField.scrollIntoView({ block: "center" });
          }
        });
      }
    );

    var filePanel = workspace.querySelector("[data-file-import]");
    Array.prototype.forEach.call(
      workspace.querySelectorAll("[data-open-file-import]"),
      function (link) {
        link.addEventListener("click", function (event) {
          if (!filePanel) { return; }
          event.preventDefault();
          filePanel.open = true;
          if (fileInput) {
            fileInput.focus({ preventScroll: true });
            if (fileInput.scrollIntoView) {
              fileInput.scrollIntoView({ block: "center" });
            }
          }
        });
      }
    );

    var dropHint = workspace.querySelector("[data-drop-hint]");
    var editorPanel = workspace.querySelector("[data-ws-panel='write']");
    if (dropHint && editorPanel && fileForm && fileInput) {
      dropHint.hidden = false;
      var dragDepth = 0;
      var setDrag = function (on) {
        editorPanel.classList.toggle("is-dragover", on);
      };
      var isFileDrag = function (event) {
        var types = event.dataTransfer && event.dataTransfer.types;
        return !!types && Array.prototype.indexOf.call(types, "Files") !== -1;
      };
      ["dragenter", "dragover"].forEach(function (name) {
        editorPanel.addEventListener(name, function (event) {
          if (!isFileDrag(event)) { return; }
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          if (name === "dragenter") { dragDepth += 1; }
          setDrag(true);
        });
      });
      editorPanel.addEventListener("dragleave", function () {
        dragDepth = Math.max(0, dragDepth - 1);
        if (dragDepth === 0) { setDrag(false); }
      });
      editorPanel.addEventListener("drop", function (event) {
        var files = event.dataTransfer ? event.dataTransfer.files : null;
        if (!files || !files.length) { return; }
        event.preventDefault();
        dragDepth = 0;
        setDrag(false);
        if (files.length !== 1) {
          announce("Choose exactly one file to import.");
          return;
        }
        try {
          var transfer = new DataTransfer();
          transfer.items.add(files[0]);
          fileInput.files = transfer.files;
        } catch (error) {
          announce("This browser cannot attach the dropped file. Use the file picker instead.");
          return;
        }
        syncImportFields();
        announce("Validating the dropped file. Nothing is replaced until you confirm.");
        if (fileForm.requestSubmit) { fileForm.requestSubmit(); } else { fileForm.submit(); }
      });
    }

    /* ---- rules drawer ---------------------------------------------------- */
    var drawer = workspace.querySelector("[data-rules-drawer]");
    var drawerTrigger = null;
    var ruleItems = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-rule-item]")
    );
    var ruleSearch = workspace.querySelector("[data-rule-search]");
    var ruleFilters = Array.prototype.slice.call(
      workspace.querySelectorAll("[data-rule-filter]")
    );
    var ruleFilter = "all";

    var filterRules = function () {
      if (!ruleItems.length) { return; }
      var query = ruleSearch ? ruleSearch.value.trim().toLowerCase() : "";
      var shown = 0;
      ruleItems.forEach(function (item) {
        var matches = (!query || (item.getAttribute("data-search") || "").indexOf(query) !== -1)
          && (ruleFilter === "all" || item.getAttribute("data-category") === ruleFilter);
        item.hidden = !matches;
        if (matches) { shown += 1; }
      });
      announce(shown + " rule" + (shown === 1 ? "" : "s") + " shown.");
    };

    if (ruleSearch) { ruleSearch.addEventListener("input", filterRules); }
    ruleFilters.forEach(function (button) {
      button.addEventListener("click", function () {
        ruleFilter = button.getAttribute("data-rule-filter");
        ruleFilters.forEach(function (item) {
          item.setAttribute("aria-pressed", item === button ? "true" : "false");
        });
        filterRules();
      });
    });

    var openRules = function (ruleId, trigger) {
      drawerTrigger = trigger || drawerTrigger;
      if (!drawer) { return; }
      if (typeof drawer.showModal !== "function") {
        window.location.href = workspace.getAttribute("data-rules-url") || "";
        return;
      }
      ruleItems.forEach(function (item) { item.classList.remove("is-target"); });
      if (!drawer.open) { drawer.showModal(); }
      var closeButton = drawer.querySelector("[data-close-rules]");
      var target = ruleId ? drawer.querySelector("#rule-" + ruleId) : null;
      if (target) {
        if (ruleSearch) { ruleSearch.value = ""; }
        ruleFilter = "all";
        ruleFilters.forEach(function (item) {
          item.setAttribute(
            "aria-pressed", item.getAttribute("data-rule-filter") === "all"
              ? "true" : "false"
          );
        });
        filterRules();
        target.hidden = false;
        target.classList.add("is-target");
        if (target.scrollIntoView) { target.scrollIntoView({ block: "nearest" }); }
        target.focus({ preventScroll: true });
      } else if (closeButton) {
        closeButton.focus();
      }
    };

    Array.prototype.forEach.call(
      workspace.querySelectorAll("[data-open-rules], [data-open-rule]"),
      function (link) {
        link.addEventListener("click", function (event) {
          if (!drawer || typeof drawer.showModal !== "function") { return; }
          event.preventDefault();
          openRules(link.getAttribute("data-open-rule"), link);
        });
      }
    );

    if (drawer) {
      var closeRules = drawer.querySelector("[data-close-rules]");
      if (closeRules) {
        closeRules.addEventListener("click", function () { drawer.close(); });
      }
      drawer.addEventListener("close", function () {
        ruleItems.forEach(function (item) { item.classList.remove("is-target"); });
        if (drawerTrigger && typeof drawerTrigger.focus === "function") {
          drawerTrigger.focus();
        }
      });
      drawer.addEventListener("click", function (event) {
        if (event.target === drawer) { drawer.close(); }
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") { return; }
      if (workspace.classList.contains("is-editor-expanded")) {
        setExpanded(false);
        if (expandButton) { expandButton.focus(); }
      }
    });

    /* ---- submit states, reviews, unsaved work ---------------------------- */
    var showReviewError = function (message) {
      if (!reviewLive) { return; }
      reviewLive.textContent = message;
      reviewLive.hidden = false;
      if (noteField) { noteField.focus(); }
      announce(message);
    };

    if (draftForm) {
      draftForm.addEventListener("submit", function (event) {
        if (submitting) { event.preventDefault(); return; }
        var submitter = event.submitter;
        if (submitter && submitter.getAttribute("data-review-outcome") === "changes"
            && noteField && !noteField.value.trim()) {
          event.preventDefault();
          showReviewError("Add an actionable note before recording Needs changes.");
          return;
        }
        submitting = true;
        var action = (submitter && submitter.formAction) || "";
        if (!action || action.indexOf("/workspace/check") !== -1
            || action.indexOf("/workspace") === -1) {
          setStatus("checking", "Checking", "Running the configured checks on this snapshot.");
          if (runButton) {
            runButton.disabled = true;
            runButton.setAttribute("aria-busy", "true");
            runButton.textContent = "Checking…";
          }
          announce("Checking draft…");
        } else if (submitter && submitter.hasAttribute("data-new-draft")) {
          announce("Checking for unsaved work before starting a new draft.");
        }
        if (action.indexOf("/workspace/export") !== -1) {
          /* A download keeps this page open, so release the guard promptly. */
          window.setTimeout(function () { submitting = false; }, 600);
        }
      });
    }

    /* Any submit inside the desk (including the separate import form) is a
       deliberate action, not "leaving" the draft by accident. */
    workspace.addEventListener("submit", function (event) {
      if (!event.defaultPrevented) { submitting = true; }
    });

    var hasWork = function () {
      if (!draftForm) { return false; }
      var title = draftForm.elements.title;
      var body = draftForm.elements.body;
      var notes = draftForm.elements.notes;
      return !!((title && title.value.trim())
        || (body && body.value.trim())
        || (notes && notes.value.trim()));
    };

    /* Bubble phase: a link that its own handler already handled (the rules
       drawer, Back to findings) has called preventDefault by now and must
       not trigger a leave-page confirmation. */
    document.addEventListener("click", function (event) {
      if (event.defaultPrevented) { return; }
      var link = event.target.closest ? event.target.closest("a[href]") : null;
      if (!link || submitting || !hasWork()) { return; }
      if (link.target === "_blank" || link.hasAttribute("download")) { return; }
      if (link.hasAttribute("data-open-rules") || link.hasAttribute("data-open-rule")
          || link.hasAttribute("data-back-findings")) { return; }
      var target;
      try {
        target = new URL(link.href, window.location.href);
      } catch (error) {
        return;
      }
      if (target.origin !== window.location.origin) { return; }
      if (target.pathname === window.location.pathname && target.hash) { return; }
      var message = "This guest draft is not saved in Lekhani. Export a review " +
        "pack to keep a copy before leaving. Leave and discard the draft?";
      if (!window.confirm(message)) {
        event.preventDefault();
      } else {
        submitting = true;
      }
    });

    window.addEventListener("beforeunload", function (event) {
      if (submitting || !hasWork()) { return; }
      event.preventDefault();
      event.returnValue = "";
    });
  }

  /* ---- printable review summary ------------------------------------------- */
  Array.prototype.forEach.call(document.querySelectorAll("[data-print-now]"), function (button) {
    button.addEventListener("click", function () { window.print(); });
  });
})();
