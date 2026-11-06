"use strict";

// The install command stays selectable when JavaScript or clipboard access is unavailable.
document.querySelectorAll("[data-copy]").forEach((button) => {
  const command = document.getElementById(button.dataset.copy);
  const status = document.getElementById("copy-status");
  let reset;
  button.hidden = false;
  button.addEventListener("click", async () => {
    clearTimeout(reset);
    try {
      await navigator.clipboard.writeText(command.textContent.trim());
      button.textContent = "Copied";
      status.textContent = "Install command copied.";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(command);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = "Selected";
      status.textContent = "Command selected. Press Ctrl+C or Command+C to copy.";
    }
    reset = setTimeout(() => { button.textContent = "Copy"; }, 2500);
  });
});

async function startPreview() {
  const screen = document.getElementById("panel-screen");
  if (!screen) return;
  const response = await fetch("designs.json");
  if (!response.ok) return;
  const designs = await response.json();
  if (designs.length < 2) return;

  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const controls = document.getElementById("preview-controls");
  const pause = document.getElementById("pause-designs");
  const previous = document.getElementById("previous-design");
  const next = document.getElementById("next-design");
  const name = document.getElementById("design-name");
  const count = document.getElementById("design-count");
  let index = 0;
  let paused = false;
  let visible = true;
  let busy = false;
  let focusSuspended = false;
  let timer;
  let finishFade = () => {};
  const canRotate = () => !paused && !motion.matches && !document.hidden && visible && !focusSuspended;

  function schedule() {
    clearTimeout(timer);
    if (canRotate() && !busy) {
      timer = setTimeout(() => { show(index + 1, true); }, 4200);
    }
  }

  function updatePause() {
    // Reduced motion never rotates, so there is nothing to pause.
    pause.hidden = motion.matches;
    pause.textContent = paused ? "Play" : "Pause";
    pause.setAttribute("aria-label", paused ? "Resume design rotation" : "Pause design rotation");
  }

  async function show(target, automatic = false) {
    if (busy) return;
    clearTimeout(timer);
    busy = true;
    const selected = (target + designs.length) % designs.length;
    const design = designs[selected];
    const old = screen.querySelector("img");
    const incoming = new Image(1600, 1600);
    incoming.className = "panel-image incoming";
    incoming.alt = `The ${design.name} design (${design.alt}), with demo readings`;
    incoming.sizes = old.sizes;
    incoming.srcset = [400, 640, 960, 1280].map((width) => `images/${design.name}-${width}.webp ${width}w`).join(", ");
    incoming.src = `images/${design.name}-640.webp`;
    try {
      await incoming.decode();
      if (automatic && !canRotate()) {
        busy = false;
        schedule();
        return;
      }
      // A changed preference stops an in-flight transition as well as the timer.
      screen.append(incoming);
      old.setAttribute("aria-hidden", "true");
      name.textContent = design.name;
      count.textContent = `${String(selected + 1).padStart(2, "0")} / ${designs.length}`;
      index = selected;
      let fadeTimer;
      finishFade = () => {
        clearTimeout(fadeTimer);
        old.remove();
        incoming.className = "panel-image";
        busy = false;
        finishFade = () => {};
        schedule();
      };
      if (motion.matches) {
        finishFade();
      } else {
        // Commit the transparent starting state before the crossfade.
        incoming.getBoundingClientRect();
        incoming.classList.add("visible");
        fadeTimer = setTimeout(finishFade, 700);
      }
    } catch {
      incoming.remove();
      old.removeAttribute("aria-hidden");
      busy = false;
      // Keep the last working frame and allow a manual retry without a request loop.
      paused = true;
      updatePause();
    }
  }

  function manual(direction) {
    paused = true;
    updatePause();
    show(index + direction);
  }
  previous.addEventListener("click", () => manual(-1));
  next.addEventListener("click", () => manual(1));
  pause.addEventListener("click", () => {
    paused = !paused;
    if (!paused) focusSuspended = false;
    updatePause();
    schedule();
  });
  // Pause on keyboard focus so an image cannot change while its controls are being read.
  controls.addEventListener("focusin", () => {
    focusSuspended = true;
    clearTimeout(timer);
  });
  controls.addEventListener("focusout", (event) => {
    if (!controls.contains(event.relatedTarget)) {
      focusSuspended = false;
      schedule();
    }
  });
  motion.addEventListener("change", () => {
    finishFade();
    updatePause();
    schedule();
  });
  document.addEventListener("visibilitychange", schedule);
  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    schedule();
  });
  observer.observe(screen);
  controls.hidden = false;
  updatePause();
  schedule();
}

// A failed catalog request leaves the initial real render and the rest of the page usable.
startPreview().catch(() => {});
