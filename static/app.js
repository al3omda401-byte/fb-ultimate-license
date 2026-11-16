// أداة صغيرة: إظهار/إخفاء خانة الأيام للمدة المخصصة + تغيير ألوان الحالة
document.addEventListener("DOMContentLoaded", () => {
  const planSelect = document.getElementById("plan-select");
  const daysBox = document.getElementById("custom-days-box");
  const sync = () => {
    if (!planSelect || !daysBox) return;
    daysBox.style.display = planSelect.value === "custom" ? "" : "none";
  };
  if (planSelect) { planSelect.addEventListener("change", sync); sync(); }

  // تنبيه عند مغادرة الصفحة وعمليات معلّقة؟ لا — بس تأكيد الفورمات الحساسة
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!confirm(form.getAttribute("data-confirm"))) event.preventDefault();
    });
  });
});
