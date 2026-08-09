const aboutNav = document.querySelector('.about-page nav');
let navUpdateFrame = null;
let lastNavOpacity = null;

const updateNavBackground = () => {
    const opacity = Math.min(window.scrollY / 250, 1) * 0.72;
    if (opacity !== lastNavOpacity) {
        aboutNav.style.setProperty('--nav-opacity', opacity);
        lastNavOpacity = opacity;
    }
    navUpdateFrame = null;
};

if (aboutNav) {
    window.addEventListener('scroll', () => {
        if (navUpdateFrame === null) navUpdateFrame = requestAnimationFrame(updateNavBackground);
    }, { passive: true });
    updateNavBackground();
}
