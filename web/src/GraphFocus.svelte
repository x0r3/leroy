<script lang="ts">
  import { untrack } from 'svelte';
  import { useNodesInitialized, useViewportInitialized, useSvelteFlow } from '@xyflow/svelte';

  let {nodeId, runId, width, height}: {nodeId:string; runId:string; width:number; height:number}=$props();
  const nodesReady=useNodesInitialized(), viewportReady=useViewportInitialized();
  const {getInternalNode, getViewport, setCenter}=useSvelteFlow();

  $effect(()=>{
    const id=nodeId, w=width, h=height;
    runId;
    if(!nodesReady.current||!viewportReady.current||!w||!h)return;
    // Pan/zoom and live duration updates must not reset a user's viewport.
    untrack(()=>{
      const node=getInternalNode(id);
      if(!node?.measured.width||!node.measured.height)return;
      const position=node.internals.positionAbsolute, viewport=getViewport();
      const left=position.x*viewport.zoom+viewport.x, top=position.y*viewport.zoom+viewport.y;
      const right=left+node.measured.width*viewport.zoom, bottom=top+node.measured.height*viewport.zoom;
      if(left<16||top<16||right>w-16||bottom>h-16){
        void setCenter(position.x+node.measured.width/2, position.y+node.measured.height/2, {zoom:viewport.zoom});
      }
    });
  });
</script>
