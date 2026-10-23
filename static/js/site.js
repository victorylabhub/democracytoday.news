(function () {
  "use strict";
  var tz = "America/New_York";
  // Newsroom invitations and password resets land on the home page; hand them to the panel.
  if (/(invite_token|recovery_token|confirmation_token|email_change_token)=/.test(location.hash)) {
    location.replace("/admin/" + location.hash);
    return;
  }
  try {
    var el = document.querySelector("[data-today]");
    if (el) {
      el.textContent = new Intl.DateTimeFormat("en-US", {
        weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: tz
      }).format(new Date());
    }
  } catch (e) { /* keep server-rendered date */ }

  // Election countdown, counted in Eastern Time calendar days.
  var cd = document.querySelector("[data-countdown]");
  if (cd) {
    try {
      var parts = cd.getAttribute("data-countdown").split("-").map(Number);
      var target = Date.UTC(parts[0], parts[1] - 1, parts[2]);
      var nowET = new Date(new Date().toLocaleString("en-US", { timeZone: tz }));
      var today = Date.UTC(nowET.getFullYear(), nowET.getMonth(), nowET.getDate());
      var days = Math.round((target - today) / 86400000);
      if (days > 1) cd.textContent = days + " days · Election guide ›";
      else if (days === 1) cd.textContent = "Tomorrow · Election guide ›";
      else if (days === 0) cd.textContent = "Today · Results & updates ›";
    } catch (e) { /* keep fallback text */ }
  }

  // Close the sections menu on Escape or outside click.
  var menus = document.querySelectorAll("details.menu");
  document.addEventListener("click", function (ev) {
    menus.forEach(function (m) { if (m.open && !m.contains(ev.target)) m.open = false; });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") menus.forEach(function (m) {
      if (m.open) { m.open = false; m.querySelector("summary").focus(); }
    });
  });
})();
