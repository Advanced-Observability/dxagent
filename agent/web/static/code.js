var graph_data = {
  container: document.getElementById('cy'),

  style: cytoscape.stylesheet()
    .selector('node')
      .css({
        'width': '100px',
        'height': '100px',
        'content': "data(name)",    
        //'data(name)',//+'\n'+'data(health)',
        'pie-size': '80%',
        'pie-1-background-color': '#E8747C',
        'pie-1-background-size': 'mapData(red, 0, 10, 0, 100)',
        'pie-2-background-color': '#74E883',
        'pie-2-background-size': 'mapData(green, 0, 10, 0, 100)',
        'pie-3-background-color': '#808080',
        'pie-3-background-size': 'mapData(grey, 0, 10, 0, 100)',
        'text-wrap': 'wrap',
      })
    .selector('edge')
      .css({
        'curve-style': 'bezier',
        'width': 4,
        'target-arrow-shape': 'triangle',
        'opacity': 0.5,
      })
    .selector(':selected')
      .css({
        'background-color': 'black',
        'line-color': 'black',
        'target-arrow-color': 'black',
        'source-arrow-color': 'black',
        'opacity': 1
      })
    .selector('.faded')
      .css({
        'opacity': 0.25,
        'text-opacity': 0
      }),

  elements: {
    nodes : dxnodes,
    edges: dxedges
  },
  selectionType : "additive",
  layout: {
    name: 'breadthfirst',//'cose',
    directed: true,
    padding: 10,
    spacingFactor: 3,
    animate: false,
    avoidOverlap: true,
    //componentSpacing:200,
    //nodeDimensionsIncludeLabels:true,
  },

  ready: function(){
    window.cy = this;
  }
};
var cyInstance = cytoscape(graph_data);
cyInstance.nodeHtmlLabel([
   {
       query : '.l1',
       halign: 'center', // title vertical position. Can be 'left',''center, 'right'
       valign: 'bottom', // title vertical position. Can be 'top',''center, 'bottom'
       halignBox: 'center', // title vertical position. Can be 'left',''center, 'right'
       valignBox: 'center', // title relative box vertical position. Can be 'top',''center, 'bottom'
       cssClass: '', // any classes will be as attribute of <div> container for every title     
       tpl: function(data) {
         var node = cy.nodes('[id ="'+data.id+'"]')
         console.log(node);
         if (node.selected()) { 
            return '<p class="symptom2">'+data.symptoms+'</p>';
         } 
         return "";
    }
   }
]);
