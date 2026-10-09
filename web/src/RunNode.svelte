<script lang="ts">
  import { Handle, Position } from '@xyflow/svelte';
  import { labels } from './types';
  let {data, selected=false}: {data:{label:string;status:string;duration:string;index:number},selected?:boolean}=$props();
</script>
<Handle type="target" position={Position.Left}/>
<div class:selected class="run-node {data.status}">
  <div class="node-top"><span class="node-index">{String(data.index+1).padStart(2,'0')}</span><span class="status-dot {data.status}"></span><span>{labels[data.status]||data.status}</span></div>
  <strong>{data.label}</strong><span class="node-duration">{data.duration}</span>
</div>
<Handle type="source" position={Position.Right}/>
