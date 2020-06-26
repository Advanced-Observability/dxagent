cytoscape({
  container: document.getElementById('cy'),

  style: cytoscape.stylesheet()
    .selector('node')
      .css({
        'width': '60px',
        'height': '60px',
        'content': 'data(id)',
        'pie-size': '80%',
        'pie-1-background-color': '#E8747C',
        'pie-1-background-size': 'mapData(red, 0, 10, 0, 100)',
        'pie-2-background-color': '#74E883',
        'pie-2-background-size': 'mapData(green, 0, 10, 0, 100)',
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
//    nodes: [
//      { data: { id: 'ab', red: 3, green: 7 } },
//      { data: { id: 'b', red: 6, green: 4} },
//      { data: { id: 'c', red: 2, green: 8 } },
//      { data: { id: 'd', red: 7, green: 3} },
//      { data: { id: michel, red: 2, green: 8} }
//    ],

//    edges: [
//      { data: { id: 'abe', weight: 1, source: 'ab', target: 'e' } },
//      { data: { id: 'abb', weight: 3, source: 'ab', target: 'b' } },
//      { data: { id: 'be', weight: 4, source: 'b', target: 'e' } },
//      { data: { id: 'bc', weight: 5, source: 'b', target: 'c' } },
//      { data: { id: 'ce', weight: 6, source: 'c', target: 'e' } },
//      { data: { id: 'cd', weight: 2, source: 'c', target: 'd' } },
//      { data: { id: 'de', weight: 7, source: 'd', target: 'e' } }
//    ]
  },

  layout: {
    name: 'breadthfirst',
    padding: 10
  },

  ready: function(){
    window.cy = this;
  }
});
