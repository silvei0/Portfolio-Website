const projectsNav = document.querySelector('.projects-page nav');

const updateProjectsNav = () => {
    const opacity = Math.min(window.scrollY / 250, 1) * 0.72;
    projectsNav.style.setProperty('--projects-nav-opacity', opacity);
};

window.addEventListener('scroll', updateProjectsNav, { passive: true });
updateProjectsNav();
