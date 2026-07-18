const sayHiButton = document.querySelector('.say-hi');

sayHiButton.addEventListener('click', () => {
    sayHiButton.textContent = 'Hi! 👋';
    sayHiButton.classList.add('clicked');
});

document.querySelectorAll('.post-it').forEach(postIt => {
    let x, y;

    postIt.onpointerdown = event => {
        x = event.clientX - postIt.offsetLeft;
        y = event.clientY - postIt.offsetTop;
        postIt.setPointerCapture(event.pointerId);
    };

    postIt.onpointermove = event => {
        if (!postIt.hasPointerCapture(event.pointerId)) return;
        postIt.style.left = event.clientX - x + 'px';
        postIt.style.top = event.clientY - y + 'px';
    };
});
