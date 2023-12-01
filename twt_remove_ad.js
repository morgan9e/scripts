// ==UserScript==
// @name         Twitter Remove Ad
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  try to take over the world!
// @author       You
// @match        https://twitter.com/home
// @icon         https://www.google.com/s2/favicons?sz=64&domain=twitter.com
// @grant        none
// ==/UserScript==

(function() {
    let removead = setInterval( function(){
        console.log("Checking ad..");
        [...document.querySelectorAll("div[data-testid=cellInnerDiv]")].forEach(e => {
            var ad = 0;
            [...e.getElementsByTagName("span")].forEach(f => {
                if (f.innerText == "Ad") {
                    ad = 1;
                }
            });
            if( ad ) {
                console.log(e.querySelectorAll("div[data-testid=User-Name]")[0].innerText);
                e.innerHTML = "";
            }
        });
    }, 1000);
})();
