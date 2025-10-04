var c = document.getElementById("myCanvas");
var ctx = c.getContext("2d");
const HEIGHT = 28
const WIDTH = 28
ratio = c.height/HEIGHT


// if(document.getElementById('info').getBoundingClientRect().width > document.getElementById('myCanvas').getBoundingClientRect().x &&
// document.getElementById('info').getBoundingClientRect().y < document.getElementById('myCanvas').getBoundingClientRect().height ){
//   console.log("overlaping divs info and canvas")
//   document.getElementById('info').style.margin =  `${document.getElementById('submitData').getBoundingClientRect().y + 30}px 0px 0px 0px`;
//   document.getElementById('info').style.fontSize = "xx-large";
//   document.getElementById('submitDataBlock').style.fontSize = "xx-large";
//   document.getElementById('prediction').style.fontSize = "xx-large";
// }else{
//   document.getElementById('info').style.margin =  `0px 0px 0px 0px`
// }
//everyone else
c.addEventListener('mousedown', startPainting);
c.addEventListener('mouseup', stopPainting);
c.addEventListener('mousemove', sketch);
//for mobile devices
c.addEventListener('pointerdown', startPainting);
c.addEventListener('pointerup', stopPainting);
c.addEventListener('pointermove', sketch);

var bufferSpace = 2;//in px
bufferSpace = bufferSpace/ratio;//converts buffer space into the fractional value

lineCountX = (HEIGHT)-1;
lineCountY = (WIDTH)-1;

var boxGridX = [];
var boxGridY = [];
//creates the grid
makeGrid()
function makeGrid(){
  ctx.fillStyle = "darkgrey";
  ctx.fillRect(0, 0, c.width, c.height);

  ctx.beginPath();
  for(let a = 1; a < (WIDTH); a++){
    //creates the lines vertical lines
    ctx.moveTo((c.width/WIDTH)*a,0);
    ctx.lineTo((c.width/WIDTH)*a,c.height);
    //recreates the lines casue they are not fully black before
    ctx.moveTo((c.width/WIDTH)*a,c.height);
    ctx.lineTo((c.width/WIDTH)*a,0);
    //makes em black
    ctx.strokeStyle = "black";
  }
  for(let b = 1; b < (HEIGHT); b++){
    //creates the lines horizontal lines
    ctx.moveTo(0,(c.height/HEIGHT)*b);
    ctx.lineTo(c.width,(c.height/HEIGHT)*b);
    //recreates the lines casue they are not fully black before
    ctx.moveTo(c.width,(c.height/HEIGHT)*b);
    ctx.lineTo(0,(c.height/HEIGHT)*b);
    //makes em black
    ctx.strokeStyle = "black";
  }
  ctx.stroke();
}

// Stores the initial position of the cursor
let coord = {x:0 , y:0};
let paint = false;
function getPosition(event){
  coord.x = event.clientX - c.offsetLeft;
  coord.y = event.clientY - c.offsetTop;
  coord.xGrid = coord.x/ratio;
  coord.yGrid = coord.y/ratio;
}
function startPainting(event){
  // document.getElementById('submitDataBlock').style.display = 'block';
  document.getElementById('prediction').style.display = 'none';
  paint = true;
  getPosition(event);
}
function stopPainting(){
  paint = false;
}
function sketch(event){
  if (!paint) return;
  getPosition(event);
  if(coord.xGrid-Math.floor(coord.xGrid) > bufferSpace && coord.yGrid-Math.floor(coord.yGrid) > bufferSpace){
    ctx.fillStyle = "white";
    ctx.fillRect(Math.floor(coord.xGrid)*ratio,Math.floor(coord.yGrid)*ratio,ratio-1,ratio-1);
    boxGridX.push(Math.floor(coord.xGrid));
    boxGridY.push(Math.floor(coord.yGrid));
  }
}
function clearScreen(){
  makeGrid()
  boxGridX.length = 0;
  boxGridY.length = 0;
}
