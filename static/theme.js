/* Applied before first paint to avoid a light/dark flash. */
(function () {
  var t = localStorage.getItem("enfactum_ai_theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
})();
