const aboutNav = document.querySelector('.about-page nav');

const updateNavBackground = () => {
    const opacity = Math.min(window.scrollY / 250, 1) * 0.72;
    aboutNav.style.setProperty('--nav-opacity', opacity);
};

window.addEventListener('scroll', updateNavBackground, { passive: true });
updateNavBackground();
