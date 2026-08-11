/*
 * Step-by-step GeoGebra scene player.
 *
 * The engine owns the applet and the construction; the page owns the UI and
 * gets told about every state change through `onState`. Two pages use it: the
 * standalone viewer (scripts/geogebra_viewer/index.html) and the side panel of
 * the scoring site, so it must not touch any DOM it was not handed.
 *
 * Requires deployggb.js to be loaded first.
 */
(function (global) {
  "use strict";

  var KNOWN_APPS = { classic: 1, geometry: 1, graphing: 1, "3d": 1, suite: 1 };

  // Scripting commands (SetColor, ZoomFit, Delete, …) create no object, so
  // evalCommand returns false even when they worked. Only construction
  // commands can be judged by the return value.
  var SCRIPTING = /^\s*(Set[A-Za-z]+|Show[A-Za-z]*|Delete|Rename|Zoom[A-Za-z]*|Pan|CenterView|SelectObject|UpdateConstruction|StartAnimation|StartRecord|PlaySound|Turtle[A-Za-z]*|Export[A-Za-z]*|Repeat|Parse)\s*\(/;

  var PLAY_MS = 1600;

  function normalize(raw) {
    var s = raw && typeof raw === "object" ? raw : {};
    return {
      title: s.title || "",
      source: s.source || "",
      app: s.app || "classic",
      view: s.view && typeof s.view === "object" ? s.view : {},
      setup: Array.isArray(s.setup) ? s.setup : [],
      steps: Array.isArray(s.steps) && s.steps.length
        ? s.steps
        : [{ title: "Пустая сцена", commands: [] }]
    };
  }

  function appName(scene) {
    return KNOWN_APPS[scene.app] ? scene.app : "classic";
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function create(options) {
    var mount = options.mount;
    var onState = options.onState || function () {};

    var scene = null;
    var applet = null;
    var appletApp = null;
    var step = 0;
    var failures = [];
    var notes = [];
    var fittedView = null;
    var playTimer = null;
    var pendingStep = null;

    function note(message) {
      notes.push(String(message));
      emit();
    }

    function emit() {
      onState({
        scene: scene,
        step: step,
        total: scene ? scene.steps.length : 0,
        failures: failures,
        notes: notes,
        playing: playTimer !== null,
        ready: applet !== null
      });
    }

    /* ---------- construction ---------- */

    function run(commands, stepIndex, collect) {
      for (var i = 0; i < commands.length; i++) {
        var cmd = commands[i];
        if (typeof cmd !== "string" || !cmd.trim()) { continue; }
        var ok = false;
        try {
          ok = applet.evalCommand(cmd) !== false;
        } catch (e) {
          ok = false;
        }
        if (!ok && collect && !SCRIPTING.test(cmd)) {
          failures.push({ step: stepIndex, command: cmd });
        }
      }
    }

    // Grow a requested window to the container's aspect ratio instead of
    // stretching it: setCoordSystem would happily give the axes different
    // scales, and then every circle is drawn as an ellipse.
    function fitAspect(box) {
      var aspect = (mount.clientWidth || 4) / (mount.clientHeight || 3);
      var w = box.xmax - box.xmin;
      var h = box.ymax - box.ymin;
      if (!(w > 0 && h > 0 && isFinite(aspect) && aspect > 0)) { return box; }
      var cx = (box.xmin + box.xmax) / 2;
      var cy = (box.ymin + box.ymax) / 2;
      if (w / h < aspect) { w = h * aspect; } else { h = w / aspect; }
      return { xmin: cx - w / 2, xmax: cx + w / 2, ymin: cy - h / 2, ymax: cy + h / 2 };
    }

    function setWindow(box) {
      if (typeof box.xmin !== "number" || typeof box.xmax !== "number") { return; }
      if (typeof box.zmin === "number") {
        applet.setCoordSystem(box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax, true);
        return;
      }
      var fitted = fitAspect(box);
      applet.setCoordSystem(fitted.xmin, fitted.xmax, fitted.ymin, fitted.ymax);
    }

    function applyView(view) {
      var axes = view.axes === true;
      try { applet.setAxesVisible(axes, axes); } catch (e) {}
      try { applet.setGridVisible(view.grid === true); } catch (e) {}
      setWindow(fittedView || view);
    }

    // The window of the step currently shown, so a resize can restore it.
    function applyCurrentView() {
      if (!applet || !scene) { return; }
      applyView(scene.view);
      var zoom = scene.steps[step] && scene.steps[step].view;
      if (zoom && typeof zoom.xmin === "number") { setWindow(zoom); }
    }

    // Objects created through evalCommand carry no label, and an unlabelled
    // picture cannot be read against the text of a solution.
    function applyLabels() {
      var mode = scene.view.labels || "points";
      if (mode === "none") { return; }
      var count = applet.getObjectNumber();
      for (var i = 0; i < count; i++) {
        var name = applet.getObjectName(i);
        if (mode === "all" || applet.getObjectType(name) === "point") {
          applet.setLabelVisible(name, true);
        }
      }
    }

    // Highlight commands are best-effort: SetPointSize on a segment simply
    // fails, and that is not a scene error, so these are never collected.
    function highlight(names) {
      if (!Array.isArray(names)) { return; }
      for (var i = 0; i < names.length; i++) {
        var n = names[i];
        if (typeof n !== "string" || !n.trim()) { continue; }
        applet.evalCommand("SetColor(" + n + ",0.72,0.11,0.11)");
        applet.evalCommand("SetLineThickness(" + n + ",7)");
        applet.evalCommand("SetPointSize(" + n + ",7)");
      }
    }

    // ZoomFit() is useless here: lines and rays are infinite, so it zooms far
    // out. Points and circles are what has to be on screen.
    function contentBounds(pad, onlyVisible) {
      var xs = [], ys = [];
      var names = [];
      var count = applet.getObjectNumber();
      for (var i = 0; i < count; i++) { names.push(applet.getObjectName(i)); }

      for (var j = 0; j < names.length; j++) {
        var name = names[j];
        if (onlyVisible) {
          try { if (!applet.getVisible(name, 1)) { continue; } } catch (e) { continue; }
        }
        var type = applet.getObjectType(name);
        if (type === "point") {
          var x = applet.getXcoord(name), y = applet.getYcoord(name);
          if (isFinite(x) && isFinite(y)) { xs.push(x, x); ys.push(y, y); }
        } else if (type === "circle") {
          // The API has no direct centre/radius getter for a conic, so ask
          // GeoGebra for them through throwaway objects.
          applet.evalCommand("ggbTmpCentre=Center(" + name + ")");
          applet.evalCommand("ggbTmpRadius=Radius(" + name + ")");
          var cx = applet.getXcoord("ggbTmpCentre");
          var cy = applet.getYcoord("ggbTmpCentre");
          var r = applet.getValue("ggbTmpRadius");
          applet.evalCommand("Delete(ggbTmpCentre)");
          applet.evalCommand("Delete(ggbTmpRadius)");
          if (isFinite(cx) && isFinite(cy) && isFinite(r) && r > 0) {
            xs.push(cx - r, cx + r);
            ys.push(cy - r, cy + r);
          }
        }
      }
      if (!xs.length) { return null; }

      var xmin = Math.min.apply(null, xs), xmax = Math.max.apply(null, xs);
      var ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys);
      var cx0 = (xmin + xmax) / 2, cy0 = (ymin + ymax) / 2;
      var w = (xmax - xmin) * (1 + 2 * pad);
      var h = (ymax - ymin) * (1 + 2 * pad);
      // A single point (or a vertical pair) has no extent in some direction.
      var span = Math.max(w, h, 1e-6);
      if (w < span * 0.02) { w = span; }
      if (h < span * 0.02) { h = span; }
      return { xmin: cx0 - w / 2, xmax: cx0 + w / 2, ymin: cy0 - h / 2, ymax: cy0 + h / 2 };
    }

    function firstFit(done) {
      var view = scene.view;
      // "step" reframes on every step instead, so nothing to precompute here.
      if (typeof view.xmin === "number" || view.fit === false
          || view.fit === "step" || appName(scene) === "3d") {
        done();
        return;
      }
      try {
        applet.newConstruction();
        run(scene.setup, -1, false);
        for (var i = 0; i < scene.steps.length; i++) {
          run(scene.steps[i].commands || [], i, false);
        }
        fittedView = contentBounds(typeof view.padding === "number" ? view.padding : 0.12, false);
      } catch (e) {
        fittedView = null;
        note("автоподбор окна не сработал: " + e);
      }
      done();
    }

    function rebuild(target) {
      if (!applet || !scene) { return; }
      step = clamp(target, 0, scene.steps.length - 1);
      failures = [];
      applet.setRepaintingActive(false);
      try {
        applet.newConstruction();
        applyView(scene.view);
        run(scene.setup, -1, true);
        for (var i = 0; i <= step; i++) {
          run(scene.steps[i].commands || [], i, true);
        }
        applyLabels();
        // With fit: "step" the window follows whatever the step actually
        // shows, which is what a scene that swaps whole pictures needs.
        if (scene.view.fit === "step") {
          var framed = contentBounds(
            typeof scene.view.padding === "number" ? scene.view.padding : 0.12,
            true
          );
          if (framed) { setWindow(framed); }
        }
        var zoom = scene.steps[step].view;
        if (zoom && typeof zoom.xmin === "number") { setWindow(zoom); }
        highlight(scene.steps[step].highlight);
      } catch (e) {
        failures.push({ step: step, command: String(e) });
      } finally {
        applet.setRepaintingActive(true);
      }
      emit();
    }

    /* ---------- applet lifecycle ---------- */

    function createApplet() {
      mount.innerHTML = "";
      applet = null;
      appletApp = appName(scene);
      var params = {
        appName: appletApp,
        // "G" is the plain graphics perspective, "T" the 3D one: only the
        // picture is wanted, the algebra pane would eat half the width.
        perspective: scene.view.perspective || (appletApp === "3d" ? "T" : "G"),
        width: mount.clientWidth || 800,
        height: mount.clientHeight || 600,
        showToolBar: false,
        showAlgebraInput: false,
        showMenuBar: false,
        showResetIcon: false,
        enableLabelDrags: false,
        enableShiftDragZoom: true,
        enableRightClick: true,
        capturingThreshold: null,
        errorDialogsActive: false,
        useBrowserForJS: false,
        ggbBase64: "",
        appletOnLoad: function (api) {
          applet = api;
          firstFit(function () { rebuild(step); });
        }
      };
      new global.GGBApplet(params, true).inject(mount);
    }

    /* ---------- public API ---------- */

    function setScene(raw) {
      var prevApp = scene ? appName(scene) : null;
      scene = normalize(raw);
      fittedView = null;
      notes = [];
      if (pendingStep !== null) {
        step = pendingStep - 1;
        pendingStep = null;
      }
      step = clamp(step, 0, scene.steps.length - 1);
      emit();
      if (!applet || prevApp !== appName(scene)) {
        createApplet();
      } else {
        firstFit(function () { rebuild(step); });
      }
    }

    function stop() {
      if (playTimer) { clearInterval(playTimer); playTimer = null; }
    }

    return {
      setScene: setScene,
      startAt: function (oneBasedStep) { pendingStep = oneBasedStep; },
      goto: function (k) { stop(); rebuild(k); },
      next: function () { stop(); rebuild(step + 1); },
      prev: function () { stop(); rebuild(step - 1); },
      first: function () { stop(); rebuild(0); },
      last: function () { stop(); rebuild(scene ? scene.steps.length - 1 : 0); },
      stop: function () { stop(); emit(); },
      togglePlay: function () {
        if (!scene) { return; }
        if (playTimer) { stop(); emit(); return; }
        if (step === scene.steps.length - 1) { rebuild(0); }
        playTimer = setInterval(function () {
          if (step >= scene.steps.length - 1) { stop(); emit(); return; }
          rebuild(step + 1);
        }, PLAY_MS);
        emit();
      },
      resize: function () {
        if (applet && mount.clientWidth) {
          applet.setSize(mount.clientWidth, mount.clientHeight);
          applyCurrentView();
        }
      },
      objectCount: function () {
        try { return applet ? applet.getObjectNumber() : 0; } catch (e) { return 0; }
      },
      note: note
    };
  }

  global.GeoGebraSteps = { create: create, normalize: normalize };
})(window);
