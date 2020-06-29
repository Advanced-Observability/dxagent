var graph_data = {
  container: document.getElementById('cy'),

  style: cytoscape.stylesheet()
    .selector('node')
      .css({
        'width': '60px',
        'height': '60px',
        'content': 'data(name)',//+'\n'+'data(health)',
        'pie-size': '80%',
        'pie-1-background-color': '#E8747C',
        'pie-1-background-size': 'mapData(red, 0, 10, 0, 100)',
        'pie-2-background-color': '#74E883',
        'pie-2-background-size': 'mapData(green, 0, 10, 0, 100)',
        'pie-3-background-color': '#808080',
        'pie-3-background-size': 'mapData(grey, 0, 10, 0, 100)',        
      })
    .selector('edge')
      .css({
        'curve-style': 'bezier',
        'width': 4,
        'target-arrow-shape': 'triangle',
        'opacity': 0.5
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

  layout: {
    name: 'breadthfirst',//'cose',
    padding: 20,
    spacingFactor: 5,
    animate: false,
    //componentSpacing:200,
    //nodeDimensionsIncludeLabels:true,
  },

  ready: function(){
    window.cy = this;
  }
};
cytoscape(graph_data);
